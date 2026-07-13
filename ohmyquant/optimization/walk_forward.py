"""策略级 walk-forward 优化

将回测区间切分为连续测试窗口，每个窗口独立运行策略，
评估策略绩效的跨周期稳定性。

与 models/walk_forward.py 的模型级 walk-forward（train/test 窗口拟合模型）
不同，本模块关注的是策略整体绩效在连续窗口上的一致性：
  - 跨牛熊周期是否持续盈利
  - Sharpe 是否稳定为正
  - 是否存在特定区间失效

Usage:
    wf = StrategyWalkForward(test_window="1Y", step="1Y")
    report = wf.run("ycj", "v1")
    print(report.summary())
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..analysis.metrics import PerformanceMetrics, compute_metrics
from ..core.logging import get_logger
from ..strategy.runner import StrategyResult, StrategyRunner

logger = get_logger(__name__)


def _parse_window(spec: str | int) -> int:
    """解析窗口规格为交易日天数

    Args:
        spec: "1Y"->252, "6M"->126, "3M"->63, "63D"->63, 或直接整数

    Returns:
        交易日天数
    """
    if isinstance(spec, int):
        return spec
    s = str(spec).strip().upper()
    if s.isdigit():
        return int(s)
    if s.endswith("Y"):
        return int(float(s[:-1]) * 252)
    if s.endswith("M"):
        return int(float(s[:-1]) * 21)
    if s.endswith("D"):
        return int(s[:-1])
    return int(s)


@dataclass
class WindowResult:
    """单窗口结果"""

    window_idx: int
    start_date: str
    end_date: str
    n_days: int
    metrics: PerformanceMetrics
    final_nav: float


@dataclass
class WalkForwardReport:
    """walk-forward 报告"""

    strategy_type: str
    version: str
    test_window: str
    step: str
    windows: list[WindowResult] = field(default_factory=list)
    mean_sharpe: float = 0.0
    std_sharpe: float = 0.0
    mean_annual_return: float = 0.0
    std_annual_return: float = 0.0
    positive_windows: int = 0
    consistency: float = 0.0

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"Walk-Forward 报告: {self.strategy_type} {self.version}",
            f"窗口规格: test={self.test_window}, step={self.step}",
            f"窗口数: {len(self.windows)}",
            "-" * 60,
            f"平均 Sharpe:     {self.mean_sharpe:>10.4f}  (std={self.std_sharpe:.4f})",
            f"平均年化收益:    {self.mean_annual_return:>10.2%}  (std={self.std_annual_return:.2%})",
            f"正 Sharpe 窗口:  {self.positive_windows}/{len(self.windows)}  "
            f"(consistency={self.consistency:.1%})",
            "-" * 60,
            "各窗口明细:",
        ]
        for w in self.windows:
            lines.append(
                f"  [{w.window_idx}] {w.start_date}~{w.end_date} "
                f"({w.n_days}d) nav={w.final_nav:.4f} "
                f"sharpe={w.metrics.sharpe_ratio:.4f} "
                f"ann_ret={w.metrics.annualized_return:.2%} "
                f"max_dd={w.metrics.max_drawdown:.2%}"
            )
        lines.append("=" * 60)
        return "\n".join(lines)


class StrategyWalkForward:
    """策略级 walk-forward 优化

    Args:
        test_window: 测试窗口规格（"1Y"/"6M"/"63D"/整数）
        step: 滑动步长（同上格式）
        min_window_days: 窗口最小交易日数，不足则跳过
    """

    def __init__(
        self,
        test_window: str | int = "1Y",
        step: str | int = "1Y",
        min_window_days: int = 42,
    ):
        self.test_window = test_window
        self.step = step
        self.test_window_days = _parse_window(test_window)
        self.step_days = _parse_window(step)
        self.min_window_days = min_window_days

    def _split_windows(
        self, dates: list[str]
    ) -> list[tuple[int, str, str]]:
        """将日期序列切分为连续测试窗口

        Returns:
            [(window_idx, start_date, end_date), ...]
        """
        n = len(dates)
        windows: list[tuple[int, str, str]] = []
        if n < self.min_window_days:
            return windows

        idx = 0
        win_idx = 0
        while idx < n:
            end_idx = min(idx + self.test_window_days, n)
            if end_idx - idx < self.min_window_days:
                break
            windows.append((win_idx, dates[idx], dates[end_idx - 1]))
            win_idx += 1
            idx += self.step_days
            # 步长大于窗口时窗口不重叠；小于时重叠，但 idx 仍前进
        return windows

    def run(
        self,
        strategy_type: str,
        version: str,
        base_overrides: dict[str, Any] | None = None,
    ) -> WalkForwardReport:
        """运行策略级 walk-forward

        Args:
            strategy_type: 策略类型（ycj/etf/dh）
            version: 版本号（v1/v2）
            base_overrides: 基础配置覆盖（如 backtest 区间、股票池）

        Returns:
            WalkForwardReport
        """
        logger.info(
            f"开始 walk-forward: {strategy_type} {version}, "
            f"test_window={self.test_window}({self.test_window_days}d), "
            f"step={self.step}({self.step_days}d)"
        )

        # 第 0 步：全程跑一次获取交易日历
        logger.info("全程回测以获取交易日历...")
        full_result: StrategyResult = StrategyRunner.run_strategy(
            strategy_type, version, base_overrides or None
        )
        all_dates = full_result.backtest_result.dates
        logger.info(f"交易日历: {len(all_dates)} 天 ({all_dates[0]}~{all_dates[-1]})")

        windows = self._split_windows(all_dates)
        if not windows:
            logger.warning("日期不足以切分任何窗口")
            return WalkForwardReport(
                strategy_type=strategy_type,
                version=version,
                test_window=str(self.test_window),
                step=str(self.step),
            )

        logger.info(f"切分为 {len(windows)} 个测试窗口")

        # 逐窗口回测
        window_results: list[WindowResult] = []
        sharpes: list[float] = []
        ann_rets: list[float] = []

        for win_idx, start_date, end_date in windows:
            logger.info(
                f"窗口 {win_idx}: {start_date}~{end_date}"
            )
            overrides = copy.deepcopy(base_overrides or {})
            bt_override = dict(overrides.get("backtest", {}))
            bt_override["start_date"] = start_date
            bt_override["end_date"] = end_date
            overrides["backtest"] = bt_override

            try:
                result = StrategyRunner.run_strategy(strategy_type, version, overrides)
            except Exception as e:
                logger.warning(f"窗口 {win_idx} ({start_date}~{end_date}) 回测失败: {e}")
                continue

            bt = result.backtest_result
            daily_returns = bt.daily_returns
            if daily_returns is None or len(daily_returns) == 0:
                logger.warning(f"窗口 {win_idx} 无 daily_returns，跳过")
                continue

            returns_arr = (
                daily_returns.to_numpy()
                if hasattr(daily_returns, "to_numpy")
                else np.asarray(daily_returns)
            )
            metrics = compute_metrics(returns_arr)
            final_nav = bt.final_nav

            window_results.append(
                WindowResult(
                    window_idx=win_idx,
                    start_date=start_date,
                    end_date=end_date,
                    n_days=bt.n_days,
                    metrics=metrics,
                    final_nav=final_nav,
                )
            )
            sharpes.append(metrics.sharpe_ratio)
            ann_rets.append(metrics.annualized_return)

        # 聚合
        report = WalkForwardReport(
            strategy_type=strategy_type,
            version=version,
            test_window=str(self.test_window),
            step=str(self.step),
            windows=window_results,
            mean_sharpe=float(np.mean(sharpes)) if sharpes else 0.0,
            std_sharpe=float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0,
            mean_annual_return=float(np.mean(ann_rets)) if ann_rets else 0.0,
            std_annual_return=float(np.std(ann_rets, ddof=1)) if len(ann_rets) > 1 else 0.0,
            positive_windows=int(np.sum(np.array(sharpes) > 0)) if sharpes else 0,
            consistency=(np.sum(np.array(sharpes) > 0) / len(sharpes)) if sharpes else 0.0,
        )

        logger.info(
            f"walk-forward 完成: {len(window_results)} 窗口, "
            f"mean_sharpe={report.mean_sharpe:.4f}, "
            f"consistency={report.consistency:.1%}"
        )

        return report


__all__ = [
    "StrategyWalkForward",
    "WalkForwardReport",
    "WindowResult",
]
