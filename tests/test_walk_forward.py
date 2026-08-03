"""walk_forward 模块单元测试

测试 ohmyquant.optimization.walk_forward 中的纯函数:
  - _parse_window: 窗口规格解析
  - StrategyWalkForward._split_windows: 窗口切分逻辑
  - WalkForwardReport.summary: 报告摘要生成
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from ohmyquant.optimization.walk_forward import (
    StrategyWalkForward,
    WalkForwardReport,
    WindowResult,
    _parse_window,
)
from ohmyquant.analysis.metrics import PerformanceMetrics


class TestParseWindow:
    """_parse_window 函数测试"""

    def test_year_suffix(self):
        assert _parse_window("1Y") == 252
        assert _parse_window("2Y") == 504

    def test_month_suffix(self):
        assert _parse_window("6M") == 126
        assert _parse_window("3M") == 63

    def test_day_suffix(self):
        assert _parse_window("63D") == 63
        assert _parse_window("100D") == 100

    def test_pure_integer(self):
        assert _parse_window(100) == 100
        assert _parse_window(252) == 252

    def test_numeric_string(self):
        assert _parse_window("100") == 100
        assert _parse_window("252") == 252

    def test_float_year(self):
        assert _parse_window("0.5Y") == 126

    def test_fallback_int_conversion(self):
        """无法识别的后缀时回退到 int() 转换"""
        with pytest.raises(ValueError):
            _parse_window("abc")


class TestSplitWindows:
    """StrategyWalkForward._split_windows 方法测试"""

    def _make_dates(self, n: int, start: str = "2020-01-01") -> list[str]:
        """生成 n 个连续日期字符串"""
        base = date.fromisoformat(start)
        return [(base + timedelta(days=i)).isoformat() for i in range(n)]

    def test_basic_non_overlapping(self):
        """步长 == 窗口大小: 无重叠切分"""
        wf = StrategyWalkForward(test_window="63D", step="63D", min_window_days=10)
        dates = self._make_dates(200)
        windows = wf._split_windows(dates)
        # 0-63, 63-126, 126-189, 189-200(11天>=10)
        assert len(windows) == 4
        assert windows[0][0] == 0  # window_idx
        assert windows[0][1] == dates[0]
        assert windows[0][2] == dates[62]

    def test_overlapping_windows(self):
        """步长 < 窗口大小: 重叠切分"""
        wf = StrategyWalkForward(test_window="100D", step="50D", min_window_days=10)
        dates = self._make_dates(200)
        windows = wf._split_windows(dates)
        # 0-100, 50-150, 100-200, 150-200(50天>=10)
        assert len(windows) == 4
        assert windows[0][1] == dates[0]
        assert windows[1][1] == dates[50]
        assert windows[2][1] == dates[100]

    def test_last_window_truncated(self):
        """最后一个窗口不足 test_window_days 但 >= min_window_days"""
        wf = StrategyWalkForward(test_window="100D", step="100D", min_window_days=10)
        dates = self._make_dates(150)
        windows = wf._split_windows(dates)
        assert len(windows) == 2  # 0-100, 100-150(50天 >= 10)
        assert windows[1][2] == dates[149]

    def test_skip_short_tail(self):
        """尾部不足 min_window_days 时不生成窗口"""
        wf = StrategyWalkForward(test_window="100D", step="100D", min_window_days=50)
        dates = self._make_dates(120)
        windows = wf._split_windows(dates)
        # 0-100 (100天 >= 50), 100-120 (20天 < 50 → 跳过)
        assert len(windows) == 1

    def test_empty_dates(self):
        """空日期列表返回空"""
        wf = StrategyWalkForward(test_window="63D", step="63D")
        assert wf._split_windows([]) == []

    def test_insufficient_dates(self):
        """日期数 < min_window_days 返回空"""
        wf = StrategyWalkForward(test_window="252D", step="252D", min_window_days=42)
        dates = self._make_dates(30)
        assert wf._split_windows(dates) == []

    def test_step_larger_than_window(self):
        """步长 > 窗口大小: 跳过部分日期"""
        wf = StrategyWalkForward(test_window="50D", step="100D", min_window_days=10)
        dates = self._make_dates(250)
        windows = wf._split_windows(dates)
        assert len(windows) == 3  # 0-50, 100-150, 200-250
        assert windows[0][1] == dates[0]
        assert windows[1][1] == dates[100]

    def test_exact_fit(self):
        """日期数正好 == test_window_days"""
        wf = StrategyWalkForward(test_window="100D", step="100D", min_window_days=10)
        dates = self._make_dates(100)
        windows = wf._split_windows(dates)
        assert len(windows) == 1
        assert windows[0][1] == dates[0]
        assert windows[0][2] == dates[99]

    def test_window_idx_sequential(self):
        """window_idx 从 0 开始递增"""
        wf = StrategyWalkForward(test_window="50D", step="50D", min_window_days=10)
        dates = self._make_dates(200)
        windows = wf._split_windows(dates)
        for i, (idx, _, _) in enumerate(windows):
            assert idx == i


class TestWalkForwardReport:
    """WalkForwardReport 测试"""

    def _make_metrics(self, sharpe: float = 1.0) -> PerformanceMetrics:
        """构造测试用 PerformanceMetrics"""
        return PerformanceMetrics(
            total_return=0.1,
            annualized_return=0.1,
            sharpe_ratio=sharpe,
            max_drawdown=-0.05,
            annualized_volatility=0.1,
            calmar_ratio=2.0,
            sortino_ratio=1.5,
            win_rate=0.55,
            n_days=252,
        )

    def test_empty_report_summary(self):
        """空窗口报告摘要"""
        report = WalkForwardReport(
            strategy_type="test",
            version="v1",
            test_window="1Y",
            step="1Y",
        )
        summary = report.summary()
        assert "test v1" in summary
        assert "窗口数: 0" in summary

    def test_report_with_windows(self):
        """有窗口的报告摘要"""
        metrics = self._make_metrics()
        report = WalkForwardReport(
            strategy_type="test",
            version="v1",
            test_window="1Y",
            step="1Y",
            windows=[
                WindowResult(0, "2020-01-01", "2020-12-31", 252, metrics, 1.1),
                WindowResult(1, "2021-01-01", "2021-12-31", 252, metrics, 1.2),
            ],
            mean_sharpe=1.0,
            std_sharpe=0.1,
            positive_windows=2,
            consistency=1.0,
        )
        summary = report.summary()
        assert "窗口数: 2" in summary
        assert "consistency=100.0%" in summary

    def test_consistency_calculation(self):
        """consistency = positive_windows / total_windows"""
        report = WalkForwardReport(
            strategy_type="test",
            version="v1",
            test_window="1Y",
            step="1Y",
            windows=[
                WindowResult(0, "2020", "2021", 252, self._make_metrics(1.0), 1.0),
                WindowResult(1, "2021", "2022", 252, self._make_metrics(-0.5), 0.95),
            ],
            positive_windows=1,
            consistency=0.5,
        )
        assert report.positive_windows == 1
        assert report.consistency == 0.5
