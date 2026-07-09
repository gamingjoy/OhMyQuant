"""归因分析

提供策略收益归因功能：
  - 持仓归因：按股票/行业分解收益贡献
  - 因子归因：按因子暴露分解收益
  - 时间归因：按时间段分解收益

功能：
  - PositionAttributor：持仓归因
  - FactorAttributor：因子归因
  - TimeAttributor：时间归因
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


class PositionAttributor:
    """持仓归因"""

    def __init__(self, positions: dict[str, np.ndarray], returns: dict[str, np.ndarray]):
        """初始化

        Args:
            positions: {股票代码: 权重序列}
            returns: {股票代码: 收益序列}
        """
        self.positions = positions
        self.returns = returns

    def compute_contribution(self) -> pl.DataFrame:
        """计算每只股票的收益贡献"""
        contributions = {}
        for code, weights in self.positions.items():
            ret = self.returns.get(code, np.zeros(len(weights)))
            contributions[code] = weights * ret[: len(weights)]

        total_contrib = np.sum(list(contributions.values()), axis=0)

        rows = []
        for code, contrib in contributions.items():
            rows.append(
                {
                    "code": code,
                    "total_contribution": np.sum(contrib),
                    "avg_contribution": np.mean(contrib),
                    "max_contribution": np.max(contrib),
                    "min_contribution": np.min(contrib),
                    "std_contribution": np.std(contrib),
                }
            )

        rows.append(
            {
                "code": "TOTAL",
                "total_contribution": np.sum(total_contrib),
                "avg_contribution": np.mean(total_contrib),
                "max_contribution": np.max(total_contrib),
                "min_contribution": np.min(total_contrib),
                "std_contribution": np.std(total_contrib),
            }
        )

        return pl.DataFrame(rows).sort("total_contribution", descending=True)


class FactorAttributor:
    """因子归因"""

    def __init__(
        self,
        factor_returns: dict[str, np.ndarray],
        factor_exposures: dict[str, np.ndarray],
    ):
        """初始化

        Args:
            factor_returns: {因子名: 因子收益序列}
            factor_exposures: {因子名: 因子暴露序列}
        """
        self.factor_returns = factor_returns
        self.factor_exposures = factor_exposures

    def compute_factor_contribution(self) -> pl.DataFrame:
        """计算各因子的收益贡献"""
        contributions = {}
        for factor, exposures in self.factor_exposures.items():
            factor_ret = self.factor_returns.get(factor, np.zeros(len(exposures)))
            contributions[factor] = exposures * factor_ret[: len(exposures)]

        total_contrib = np.sum(list(contributions.values()), axis=0)

        rows = []
        for factor, contrib in contributions.items():
            rows.append(
                {
                    "factor": factor,
                    "total_contribution": np.sum(contrib),
                    "avg_contribution": np.mean(contrib),
                    "max_contribution": np.max(contrib),
                    "min_contribution": np.min(contrib),
                    "std_contribution": np.std(contrib),
                    "avg_exposure": np.mean(exposures),
                }
            )

        rows.append(
            {
                "factor": "TOTAL",
                "total_contribution": np.sum(total_contrib),
                "avg_contribution": np.mean(total_contrib),
                "max_contribution": np.max(total_contrib),
                "min_contribution": np.min(total_contrib),
                "std_contribution": np.std(total_contrib),
                "avg_exposure": np.nan,
            }
        )

        return pl.DataFrame(rows).sort("total_contribution", descending=True)


class TimeAttributor:
    """时间归因"""

    def __init__(self, returns: np.ndarray, dates: list[str]):
        """初始化

        Args:
            returns: 每日收益序列
            dates: 日期列表
        """
        self.returns = returns
        self.dates = dates

    def compute_monthly_contribution(self) -> pl.DataFrame:
        """计算月度收益贡献"""
        monthly_contrib = {}

        for i, date in enumerate(self.dates):
            month = date[:7]
            if month not in monthly_contrib:
                monthly_contrib[month] = []
            monthly_contrib[month].append(self.returns[i])

        rows = []
        for month, rets in monthly_contrib.items():
            rows.append(
                {
                    "month": month,
                    "total_return": np.sum(rets),
                    "n_days": len(rets),
                    "avg_daily_return": np.mean(rets),
                    "std_daily_return": np.std(rets),
                    "max_daily_return": np.max(rets),
                    "min_daily_return": np.min(rets),
                }
            )

        return pl.DataFrame(rows).sort("month")

    def compute_quarterly_contribution(self) -> pl.DataFrame:
        """计算季度收益贡献"""
        quarterly_contrib = {}

        for i, date in enumerate(self.dates):
            year = date[:4]
            month = int(date[5:7])
            quarter = f"{year}Q{(month - 1) // 3 + 1}"
            if quarter not in quarterly_contrib:
                quarterly_contrib[quarter] = []
            quarterly_contrib[quarter].append(self.returns[i])

        rows = []
        for quarter, rets in quarterly_contrib.items():
            rows.append(
                {
                    "quarter": quarter,
                    "total_return": np.sum(rets),
                    "n_days": len(rets),
                    "avg_daily_return": np.mean(rets),
                    "std_daily_return": np.std(rets),
                }
            )

        return pl.DataFrame(rows).sort("quarter")


__all__ = ["PositionAttributor", "FactorAttributor", "TimeAttributor"]
