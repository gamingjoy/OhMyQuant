"""多策略对比分析

提供多策略绩效对比、相关性分析和两两组合扫描。

功能：
  - 多策略指标对比表
  - 滚动相关性分析
  - 两两策略组合优化
  - 策略排名
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .metrics import PerformanceMetrics, compute_metrics
from ..core.logging import get_logger

logger = get_logger(__name__)


class StrategyComparator:
    """策略对比器"""

    def __init__(self, strategies: dict[str, np.ndarray]):
        """初始化

        Args:
            strategies: {策略名: 每日收益序列}
        """
        self.strategies = strategies
        self.metrics: dict[str, PerformanceMetrics] = {}

    def compute_all_metrics(self) -> dict[str, PerformanceMetrics]:
        """计算所有策略的绩效指标"""
        self.metrics = {
            name: compute_metrics(returns)
            for name, returns in self.strategies.items()
        }
        return self.metrics

    def get_comparison_table(self) -> pl.DataFrame:
        """获取对比表（polars DataFrame）"""
        if not self.metrics:
            self.compute_all_metrics()

        rows = []
        for name, metrics in self.metrics.items():
            rows.append(
                {
                    "strategy": name,
                    "total_return": metrics.total_return,
                    "annualized_return": metrics.annualized_return,
                    "annualized_volatility": metrics.annualized_volatility,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "sortino_ratio": metrics.sortino_ratio,
                    "calmar_ratio": metrics.calmar_ratio,
                    "max_drawdown": metrics.max_drawdown,
                    "win_rate": metrics.win_rate,
                    "profit_factor": metrics.profit_factor,
                    "n_days": metrics.n_days,
                }
            )

        return pl.DataFrame(rows)

    def compute_correlation_matrix(self) -> pl.DataFrame:
        """计算策略间相关性矩阵"""
        names = list(self.strategies.keys())
        n = len(names)
        corr_matrix = np.eye(n)

        for i in range(n):
            for j in range(i + 1, n):
                r1 = self.strategies[names[i]]
                r2 = self.strategies[names[j]]
                min_len = min(len(r1), len(r2))
                if min_len > 1:
                    corr = np.corrcoef(r1[:min_len], r2[:min_len])[0, 1]
                    corr_matrix[i, j] = corr
                    corr_matrix[j, i] = corr

        return pl.DataFrame(corr_matrix, schema=names).with_columns(
            strategy=pl.Series(names)
        ).select(["strategy"] + names)

    def compute_rolling_correlation(
        self, strategy1: str, strategy2: str, window: int = 60
    ) -> np.ndarray:
        """计算滚动相关性"""
        r1 = self.strategies[strategy1]
        r2 = self.strategies[strategy2]
        min_len = min(len(r1), len(r2))
        r1, r2 = r1[:min_len], r2[:min_len]

        rolling_corr = np.full(len(r1), np.nan)
        for i in range(window, len(r1)):
            rolling_corr[i] = np.corrcoef(r1[i - window : i], r2[i - window : i])[0, 1]

        return rolling_corr

    def find_best_pairs(self, top_n: int = 5) -> list[dict]:
        """寻找相关性最低的策略组合（分散化效果最好）"""
        names = list(self.strategies.keys())
        pairs = []

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                r1 = self.strategies[names[i]]
                r2 = self.strategies[names[j]]
                min_len = min(len(r1), len(r2))
                if min_len > 1:
                    corr = np.corrcoef(r1[:min_len], r2[:min_len])[0, 1]
                    pairs.append(
                        {
                            "strategy1": names[i],
                            "strategy2": names[j],
                            "correlation": corr,
                        }
                    )

        pairs.sort(key=lambda x: abs(x["correlation"]))
        return pairs[:top_n]

    def combine_strategies(
        self, weights: dict[str, float]
    ) -> np.ndarray:
        """按权重组合策略"""
        min_len = min(len(self.strategies[name]) for name in weights)
        combined = np.zeros(min_len)
        total_weight = sum(weights.values())

        for name, weight in weights.items():
            combined += self.strategies[name][:min_len] * (weight / total_weight)

        return combined

    def optimize_pair_allocation(
        self, strategy1: str, strategy2: str, target_vol: float = 0.2
    ) -> dict[str, float]:
        """优化两策略组合的权重"""
        r1 = self.strategies[strategy1]
        r2 = self.strategies[strategy2]
        min_len = min(len(r1), len(r2))
        r1, r2 = r1[:min_len], r2[:min_len]

        cov_matrix = np.cov(r1, r2)
        vol1 = np.sqrt(cov_matrix[0, 0]) * np.sqrt(242)
        vol2 = np.sqrt(cov_matrix[1, 1]) * np.sqrt(242)

        if vol1 == 0 and vol2 == 0:
            return {strategy1: 0.5, strategy2: 0.5}

        w1 = vol2 / (vol1 + vol2)
        w2 = 1 - w1

        scale = target_vol / np.sqrt(
            w1**2 * cov_matrix[0, 0] + w2**2 * cov_matrix[1, 1] + 2 * w1 * w2 * cov_matrix[0, 1]
        ) * np.sqrt(242)

        return {strategy1: w1 * scale, strategy2: w2 * scale}

    def rank_strategies(self, metric: str = "sharpe_ratio") -> list[tuple[str, float]]:
        """按指标排名策略"""
        if not self.metrics:
            self.compute_all_metrics()

        reverse = True
        if metric in ["max_drawdown"]:
            reverse = False

        return sorted(
            [(name, getattr(m, metric)) for name, m in self.metrics.items()],
            key=lambda x: x[1],
            reverse=reverse,
        )

    def print_comparison(self) -> None:
        """打印对比表"""
        df = self.get_comparison_table()
        print(df.to_string())


__all__ = ["StrategyComparator"]
