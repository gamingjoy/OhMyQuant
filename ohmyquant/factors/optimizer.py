"""因子组合优化

从候选因子池中选择最优因子组合：
  1. IC 相关性过滤（去冗余）
  2. ICIR 加权
  3. 滚动因子选择
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


class FactorOptimizer:
    """因子组合优化器

    用法:
        optimizer = FactorOptimizer()
        strong = optimizer.select_strong_factors(ic_df, train_end="2024-12-31",
                                                  min_ic=0.02, min_icir=0.1)
    """

    @staticmethod
    def select_strong_factors(
        ic_df: pl.DataFrame,
        train_end: str,
        min_ic: float = 0.02,
        min_icir: float = 0.1,
        corr_threshold: float = 0.85,
        max_factors: int = 15,
    ) -> list[str]:
        """筛选强因子

        Args:
            ic_df: IC 数据，date 列 + 各因子 IC 列
            train_end: 训练集截止日期
            min_ic: IC 绝对值下限
            min_icir: ICIR 绝对值下限
            corr_threshold: 因子相关性阈值（超过则去冗余）
            max_factors: 最多保留因子数

        Returns:
            强因子名列表
        """
        # 截取训练集
        train_ic = ic_df.filter(pl.col("date") <= pl.lit(train_end).str.to_date())
        factor_cols = [c for c in train_ic.columns if c != "date"]

        if not factor_cols:
            return []

        # 计算每个因子的 IC 均值和 ICIR
        stats = []
        for col in factor_cols:
            ic_vals = train_ic[col].drop_nulls().to_numpy()
            if len(ic_vals) < 10:
                continue
            ic_mean = float(np.mean(ic_vals))
            ic_std = float(np.std(ic_vals))
            icir = ic_mean / ic_std if ic_std > 1e-8 else 0
            stats.append({"factor": col, "ic_mean": ic_mean, "ic_std": ic_std, "icir": icir})

        if not stats:
            return []

        stats_df = pl.DataFrame(stats)

        # 过滤：IC 和 ICIR 达标
        strong = stats_df.filter(
            (pl.col("ic_mean").abs() >= min_ic)
            & (pl.col("icir").abs() >= min_icir)
        ).sort("ic_mean", descending=True)

        if strong.is_empty():
            return []

        # 相关性去冗余
        corr_matrix = train_ic.select(factor_cols).corr()
        corr_matrix = corr_matrix.with_columns(pl.Series(factor_cols).alias("factor"))

        selected: list[str] = []
        for row in strong.iter_rows(named=True):
            factor = row["factor"]
            is_redundant = False
            for existing in selected:
                if existing in corr_matrix["factor"].to_list():
                    idx = corr_matrix["factor"].to_list().index(existing)
                    corr_val = corr_matrix[factor][idx]
                    if abs(corr_val) > corr_threshold:
                        is_redundant = True
                        logger.debug(
                            f"因子 {factor} 与 {existing} 相关性 {corr_val:.2f}，去冗余"
                        )
                        break
            if not is_redundant:
                selected.append(factor)
            if len(selected) >= max_factors:
                break

        logger.info(f"筛选强因子: {selected}")
        return selected

    @staticmethod
    def compute_icir_weights(
        ic_df: pl.DataFrame,
        factor_names: list[str],
        current_date: str,
        window: int = 60,
        decay: float = 0.65,
    ) -> dict[str, float]:
        """计算 ICIR 加权权重

        Args:
            ic_df: IC 数据
            factor_names: 因子列表
            current_date: 当前日期
            window: 滚动窗口
            decay: 指数衰减

        Returns:
            {factor_name: weight}
        """
        current_idx = ic_df["date"].search_sorted(current_date)
        start_idx = max(0, current_idx - window)
        recent_ic = ic_df[start_idx:current_idx]

        weights = {}
        total_weight = 0
        for factor in factor_names:
            if factor not in recent_ic.columns:
                weights[factor] = 0
                continue
            ic_vals = recent_ic[factor].drop_nulls().to_numpy()
            if len(ic_vals) < 5:
                weights[factor] = 0
                continue

            # 指数衰减加权
            n = len(ic_vals)
            if decay < 1.0:
                w = np.array([decay ** k for k in range(n)])[::-1]
                w = w / w.sum()
                ic_mean = np.average(ic_vals, weights=w)
                ic_std = np.sqrt(np.average((ic_vals - ic_mean) ** 2, weights=w))
            else:
                ic_mean = np.mean(ic_vals)
                ic_std = np.std(ic_vals)

            icir = ic_mean / ic_std if ic_std > 1e-8 else 0
            # 只保留正 ICIR 的因子
            weight = max(icir, 0)
            weights[factor] = float(weight)
            total_weight += weight

        # 归一化
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        return weights


__all__ = ["FactorOptimizer"]
