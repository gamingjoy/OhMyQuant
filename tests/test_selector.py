"""选股器单元测试

覆盖：
  - BaseSelector.apply_weight_cap（个股权重上限）
  - BaseSelector.select_strong_factors（IC 强因子筛选）
  - IndustryRotationSelector._compute_market_scale（大盘趋势过滤：bull/bear/sideways/binary/绝对动量）

注：IndustryRotationSelector.select() 依赖外部数据（行情/估值/因子），
    完整集成测试需 mock 大量数据，此处聚焦可独立验证的逻辑单元。
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import polars as pl
import pytest

from ohmyquant.engine.selector import BaseSelector
from ohmyquant.engine.selectors.industry_rotation_selector import (
    IndustryRotationSelector,
)


class _ConcreteSelector(BaseSelector):
    """BaseSelector 的具体子类（用于测试基类方法）"""

    def select(self, factors, ic_df, stock_codes, current_idx, close, regime=None,
               strong_factors=None, **kwargs):
        return {}


def _weekdays_dt(start: str, n: int) -> list[datetime]:
    """生成 n 个工作日（datetime 对象，跳过周末）"""
    dt = datetime.strptime(start, "%Y-%m-%d")
    dates = []
    while len(dates) < n:
        if dt.weekday() < 5:
            dates.append(dt)
        dt += timedelta(days=1)
    return dates


def _make_market_close(prices: list[float], start: str = "2024-01-01") -> pl.DataFrame:
    """构造大盘指数收盘价 DataFrame（datetime date + close）"""
    dates = _weekdays_dt(start, len(prices))
    return pl.DataFrame({"date": dates, "close": prices})


def _make_candidate_close(n_dates: int, start: str = "2024-01-01") -> pl.DataFrame:
    """构造候选池收盘价宽表（datetime date 列，用于日期对齐）"""
    dates = _weekdays_dt(start, n_dates)
    return pl.DataFrame({"date": dates, "000001.SZ": 10.0})


class TestApplyWeightCap:
    """个股权重上限测试"""

    def test_all_within_cap(self):
        """所有权重都在上限内时不调整"""
        sel = _ConcreteSelector({"max_stock_weight": 0.50})
        weights = {"A": 0.3, "B": 0.3, "C": 0.4}
        result = sel.apply_weight_cap(weights)
        assert result == weights

    def test_single_stock_capped(self):
        """超限股票被截断，结果归一化"""
        sel = _ConcreteSelector({"max_stock_weight": 0.25})
        # A=0.4 超过 cap=0.25，其余未超
        weights = {"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}
        result = sel.apply_weight_cap(weights, cap=0.25)
        # 截断+重分配后所有股票 <= cap（足够数量时可满足）
        assert result["A"] <= 0.25 + 1e-6
        assert pytest.approx(sum(result.values()), rel=1e-6) == 1.0

    def test_empty_weights(self):
        """空权重返回空"""
        sel = _ConcreteSelector({"max_stock_weight": 0.10})
        assert sel.apply_weight_cap({}) == {}

    def test_custom_cap(self):
        """自定义上限覆盖配置默认值"""
        sel = _ConcreteSelector({"max_stock_weight": 0.10})
        weights = {"A": 0.6, "B": 0.4}
        result = sel.apply_weight_cap(weights, cap=0.50)
        assert result["A"] <= 0.50 + 1e-6

    def test_normalizes_to_one(self):
        """结果归一化（和为1）"""
        sel = _ConcreteSelector({"max_stock_weight": 0.10})
        weights = {"A": 0.5, "B": 0.5}
        result = sel.apply_weight_cap(weights)
        assert pytest.approx(sum(result.values()), rel=1e-6) == 1.0


class TestSelectStrongFactors:
    """IC 强因子筛选测试"""

    def test_select_top_by_abs_ic(self):
        """按 IC 绝对值排序"""
        sel = _ConcreteSelector({})
        ic_df = pl.DataFrame({
            "date": pl.Series(["2024-01-01", "2024-01-02", "2024-01-03"], dtype=pl.Date),
            "f1": [0.1, 0.1, 0.1],
            "f2": [-0.3, -0.3, -0.3],
            "f3": [0.2, 0.2, 0.2],
        })
        result = sel.select_strong_factors(ic_df, "2024-01-03")
        # |IC|: f2(0.3) > f3(0.2) > f1(0.1)
        assert result[0] == "f2"
        assert result[1] == "f3"
        assert result[2] == "f1"

    def test_filters_by_train_end(self):
        """仅使用 train_end 之前的 IC 数据"""
        sel = _ConcreteSelector({})
        ic_df = pl.DataFrame({
            "date": pl.Series(["2024-01-01", "2024-01-02", "2024-01-03"], dtype=pl.Date),
            "f1": [0.1, 0.5, 0.9],
            "f2": [0.3, 0.3, 0.3],
        })
        result = sel.select_strong_factors(ic_df, "2024-01-01")
        assert result[0] == "f2"  # 0.3 > 0.1

    def test_max_15_factors(self):
        """最多返回 15 个因子"""
        sel = _ConcreteSelector({})
        data: dict = {"date": pl.Series(["2024-01-01"], dtype=pl.Date)}
        for i in range(20):
            data[f"f{i}"] = [0.01 * i]
        ic_df = pl.DataFrame(data)
        result = sel.select_strong_factors(ic_df, "2024-01-01")
        assert len(result) <= 15


class TestMarketScale:
    """大盘趋势过滤系数测试（_compute_market_scale）"""

    def _make_selector(self, **kwargs):
        cfg = {
            "industry_rotation": {
                "market_filter": True,
                "market_ma_short": 10,
                "market_ma_long": 30,
                "market_filter_binary": False,
                "absolute_momentum": False,
                **kwargs,
            }
        }
        return IndustryRotationSelector(cfg)

    def test_bull_market_full_position(self):
        """牛市：价格 > MA_short > MA_long → 1.0"""
        sel = self._make_selector()
        prices = [float(i + 1) for i in range(35)]  # 递增
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 1.0

    def test_bear_market_empty_position(self):
        """熊市：价格 < MA_long → 0.0"""
        sel = self._make_selector()
        prices = [float(35 - i) for i in range(35)]  # 递减
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 0.0

    def test_sideways_market_half_position(self):
        """震荡市：MA_long <= price < MA_short → 0.5"""
        sel = self._make_selector(market_filter_binary=False)
        # 递增后回落：短均线被拉高，当前价低于短均线但高于长均线
        prices = [float(i + 1) for i in range(30)] + [31.0, 32.0, 33.0, 34.0, 25.0]
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 0.5

    def test_binary_mode_bull(self):
        """二值模式牛市：price >= MA_long → 1.0"""
        sel = self._make_selector(market_filter_binary=True)
        prices = [float(i + 1) for i in range(35)]
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 1.0

    def test_binary_mode_bear(self):
        """二值模式熊市：price < MA_long → 0.0"""
        sel = self._make_selector(market_filter_binary=True)
        prices = [float(35 - i) for i in range(35)]
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 0.0

    def test_absolute_momentum_empty_in_binary(self):
        """二值模式 + 绝对动量：价格在 MA_long 上但近期收益为负 → 0.0"""
        sel = self._make_selector(
            market_filter_binary=True,
            absolute_momentum=True,
            absolute_momentum_window=5,
            absolute_momentum_threshold=-0.03,
        )
        # 递增至35后回落到25：current(25) > MA_long(~20)，但5日收益 25/30-1=-16.7% < -3%
        prices = [float(i + 1) for i in range(30)] + [31.0, 32.0, 33.0, 34.0, 25.0]
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 0.0

    def test_no_market_data_returns_one(self):
        """无大盘数据时返回 1.0（不过滤）"""
        sel = self._make_selector()
        candidate_close = _make_candidate_close(35)
        with patch.object(sel, "_load_market_close", return_value=None):
            scale = sel._compute_market_scale(34, candidate_close)
        assert scale == 1.0

    def test_insufficient_market_data_returns_one(self):
        """大盘数据不足 MA_long+1 时返回 1.0"""
        sel = self._make_selector()
        prices = [10.0] * 5  # 不足 31
        market_close = _make_market_close(prices)
        candidate_close = _make_candidate_close(5)
        with patch.object(sel, "_load_market_close", return_value=market_close):
            scale = sel._compute_market_scale(4, candidate_close)
        assert scale == 1.0


class TestSelectorConfig:
    """选股器配置测试"""

    def test_default_config(self):
        sel = IndustryRotationSelector({})
        assert sel.top_n == 10
        assert sel.top_industries == 5
        assert sel.stocks_per_industry == 2

    def test_custom_config(self):
        cfg = {
            "top_n": 20,
            "industry_rotation": {
                "top_industries": 3,
                "stocks_per_industry": 3,
                "market_ma_short": 5,
                "market_ma_long": 20,
            },
        }
        sel = IndustryRotationSelector(cfg)
        assert sel.top_n == 20
        assert sel.top_industries == 3
        assert sel.stocks_per_industry == 3
        assert sel.market_ma_short == 5
        assert sel.market_ma_long == 20
