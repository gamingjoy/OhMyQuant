"""绩效指标计算

提供完整的策略绩效评估指标，包括：
  - 收益指标：年化收益、累计收益
  - 风险指标：波动率、最大回撤、VaR
  - 风险调整收益：Sharpe、Sortino、Calmar、Info Ratio
  - 收益分布：偏度、峰度

输入：每日收益序列（polars Series 或 numpy array）
输出：指标字典
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)

TRADING_DAYS = 242
RISK_FREE_RATE = 0.02


@dataclass
class PerformanceMetrics:
    """绩效指标"""

    total_return: float = 0.0
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    var_95: float = 0.0
    cvar_95: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    info_ratio: float = 0.0
    n_days: int = 0

    def to_dict(self) -> dict[str, float | int]:
        """转为字典"""
        return {
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "annualized_volatility": self.annualized_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "var_95": self.var_95,
            "cvar_95": self.cvar_95,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "info_ratio": self.info_ratio,
            "n_days": self.n_days,
        }


def _to_array(returns) -> np.ndarray:
    """转换为 numpy array"""
    if isinstance(returns, pl.Series):
        return returns.to_numpy()
    if isinstance(returns, np.ndarray):
        return returns
    if isinstance(returns, list):
        return np.array(returns)
    raise TypeError(f"不支持的类型: {type(returns)}")


def compute_total_return(returns: np.ndarray) -> float:
    """计算累计收益"""
    return np.prod(1 + returns) - 1


def compute_annualized_return(returns: np.ndarray) -> float:
    """计算年化收益"""
    n_days = len(returns)
    if n_days == 0:
        return 0.0
    total_return = compute_total_return(returns)
    return (1 + total_return) ** (TRADING_DAYS / n_days) - 1


def compute_annualized_volatility(returns: np.ndarray) -> float:
    """计算年化波动率"""
    if len(returns) < 2:
        return 0.0
    return np.std(returns, ddof=1) * np.sqrt(TRADING_DAYS)


def compute_sharpe_ratio(
    returns: np.ndarray, risk_free_rate: float = RISK_FREE_RATE
) -> float:
    """计算 Sharpe 比率"""
    vol = compute_annualized_volatility(returns)
    if vol == 0:
        return 0.0
    excess_return = compute_annualized_return(returns) - risk_free_rate
    return excess_return / vol


def compute_sortino_ratio(
    returns: np.ndarray, risk_free_rate: float = RISK_FREE_RATE
) -> float:
    """计算 Sortino 比率（下行风险）"""
    downside_returns = returns[returns < 0]
    if len(downside_returns) == 0:
        return 0.0
    downside_vol = np.std(downside_returns, ddof=1) * np.sqrt(TRADING_DAYS)
    if downside_vol == 0:
        return 0.0
    excess_return = compute_annualized_return(returns) - risk_free_rate
    return excess_return / downside_vol


def compute_max_drawdown(returns: np.ndarray) -> tuple[float, int]:
    """计算最大回撤和持续时间

    Returns:
        (max_drawdown, duration)
    """
    if len(returns) == 0:
        return 0.0, 0

    cum_returns = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cum_returns)
    drawdown = (cum_returns - running_max) / running_max

    max_dd = np.min(drawdown)
    max_idx = np.argmin(drawdown)

    start_idx = np.argmax(cum_returns[: max_idx + 1])
    duration = max_idx - start_idx

    return max_dd, duration


def compute_calmar_ratio(returns: np.ndarray) -> float:
    """计算 Calmar 比率"""
    max_dd, _ = compute_max_drawdown(returns)
    if max_dd == 0:
        return 0.0
    return compute_annualized_return(returns) / abs(max_dd)


def compute_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """计算 VaR（Value at Risk）"""
    if len(returns) == 0:
        return 0.0
    return np.percentile(returns, (1 - confidence) * 100)


def compute_cvar(returns: np.ndarray, confidence: float = 0.95) -> float:
    """计算 CVaR（Conditional Value at Risk）"""
    var = compute_var(returns, confidence)
    tail_returns = returns[returns <= var]
    if len(tail_returns) == 0:
        return var
    return np.mean(tail_returns)


def compute_skewness(returns: np.ndarray) -> float:
    """计算偏度"""
    if len(returns) < 3:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=0)
    if std == 0:
        return 0.0
    return np.mean((returns - mean) ** 3) / std**3


def compute_kurtosis(returns: np.ndarray) -> float:
    """计算峰度"""
    if len(returns) < 4:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=0)
    if std == 0:
        return 0.0
    return np.mean((returns - mean) ** 4) / std**4 - 3


def compute_win_rate(returns: np.ndarray) -> float:
    """计算胜率"""
    if len(returns) == 0:
        return 0.0
    return np.sum(returns > 0) / len(returns)


def compute_avg_win_loss(returns: np.ndarray) -> tuple[float, float]:
    """计算平均盈利和平均亏损"""
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    avg_win = np.mean(wins) if len(wins) > 0 else 0.0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0.0
    return avg_win, avg_loss


def compute_profit_factor(returns: np.ndarray) -> float:
    """计算盈亏比"""
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    total_win = np.sum(wins)
    total_loss = abs(np.sum(losses))
    if total_loss == 0:
        return float("inf") if total_win > 0 else 0.0
    return total_win / total_loss


def compute_info_ratio(returns: np.ndarray, benchmark_returns: np.ndarray) -> float:
    """计算信息比率"""
    excess = returns - benchmark_returns[: len(returns)]
    tracking_error = np.std(excess, ddof=1) * np.sqrt(TRADING_DAYS)
    if tracking_error == 0:
        return 0.0
    excess_return = compute_annualized_return(excess)
    return excess_return / tracking_error


def compute_metrics(
    returns, benchmark_returns: np.ndarray | None = None
) -> PerformanceMetrics:
    """计算所有绩效指标

    Args:
        returns: 每日收益序列（polars Series / numpy array / list）
        benchmark_returns: 基准收益序列（可选）

    Returns:
        PerformanceMetrics
    """
    returns_arr = _to_array(returns)

    if len(returns_arr) == 0:
        return PerformanceMetrics()

    max_dd, max_dd_duration = compute_max_drawdown(returns_arr)
    avg_win, avg_loss = compute_avg_win_loss(returns_arr)

    info_ratio_val = 0.0
    if benchmark_returns is not None:
        info_ratio_val = compute_info_ratio(returns_arr, _to_array(benchmark_returns))

    return PerformanceMetrics(
        total_return=compute_total_return(returns_arr),
        annualized_return=compute_annualized_return(returns_arr),
        annualized_volatility=compute_annualized_volatility(returns_arr),
        sharpe_ratio=compute_sharpe_ratio(returns_arr),
        sortino_ratio=compute_sortino_ratio(returns_arr),
        calmar_ratio=compute_calmar_ratio(returns_arr),
        max_drawdown=max_dd,
        max_drawdown_duration=max_dd_duration,
        var_95=compute_var(returns_arr, 0.95),
        cvar_95=compute_cvar(returns_arr, 0.95),
        skewness=compute_skewness(returns_arr),
        kurtosis=compute_kurtosis(returns_arr),
        win_rate=compute_win_rate(returns_arr),
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=compute_profit_factor(returns_arr),
        info_ratio=info_ratio_val,
        n_days=len(returns_arr),
    )


def print_metrics(metrics: PerformanceMetrics) -> None:
    """打印绩效指标"""
    print("=" * 60)
    print("绩效指标")
    print("=" * 60)
    print(f"累计收益:        {metrics.total_return:>12.2%}")
    print(f"年化收益:        {metrics.annualized_return:>12.2%}")
    print(f"年化波动率:      {metrics.annualized_volatility:>12.2%}")
    print(f"Sharpe 比率:     {metrics.sharpe_ratio:>12.4f}")
    print(f"Sortino 比率:    {metrics.sortino_ratio:>12.4f}")
    print(f"Calmar 比率:     {metrics.calmar_ratio:>12.4f}")
    print(f"最大回撤:        {metrics.max_drawdown:>12.2%}")
    print(f"回撤持续天数:    {metrics.max_drawdown_duration:>12d}")
    print(f"VaR(95%):       {metrics.var_95:>12.2%}")
    print(f"CVaR(95%):      {metrics.cvar_95:>12.2%}")
    print(f"偏度:           {metrics.skewness:>12.4f}")
    print(f"峰度:           {metrics.kurtosis:>12.4f}")
    print(f"胜率:           {metrics.win_rate:>12.2%}")
    print(f"平均盈利:       {metrics.avg_win:>12.2%}")
    print(f"平均亏损:       {metrics.avg_loss:>12.2%}")
    print(f"盈亏比:         {metrics.profit_factor:>12.4f}")
    print(f"信息比率:       {metrics.info_ratio:>12.4f}")
    print(f"交易天数:       {metrics.n_days:>12d}")
    print("=" * 60)


__all__ = [
    "PerformanceMetrics",
    "compute_total_return",
    "compute_annualized_return",
    "compute_annualized_volatility",
    "compute_sharpe_ratio",
    "compute_sortino_ratio",
    "compute_max_drawdown",
    "compute_calmar_ratio",
    "compute_var",
    "compute_cvar",
    "compute_skewness",
    "compute_kurtosis",
    "compute_win_rate",
    "compute_avg_win_loss",
    "compute_profit_factor",
    "compute_info_ratio",
    "compute_metrics",
    "print_metrics",
]
