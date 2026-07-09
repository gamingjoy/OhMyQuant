"""ICIR 加权选股器

基于因子 ICIR 加权选股，参考 halo_index 的 ICIRSelector。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ...factors.optimizer import FactorOptimizer
from ..selector import BaseSelector

logger = get_logger(__name__)


@register_selector("icir")
class ICIRSelector(BaseSelector):
    """ICIR 加权选股器

    流程:
      1. 计算每个强因子的 ICIR 权重
      2. 对每只股票，按因子值排名 × ICIR 权重计算综合评分
      3. 取 Top-N，等权或按分数加权
      4. 应用个股权重上限
    """

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        if not strong_factors:
            return None

        # 1. 计算 ICIR 权重
        dates = ic_df["date"].to_list()
        if current_idx >= len(dates):
            return None
        current_date = dates[current_idx]
        factor_weights = FactorOptimizer.compute_icir_weights(
            ic_df, strong_factors, current_date, self.icir_window, self.ic_decay
        )

        if not any(factor_weights.values()):
            # 退化为等权
            factor_weights = {f: 1.0 / len(strong_factors) for f in strong_factors}

        # 2. 计算综合评分
        scores: dict[str, float] = {code: 0.0 for code in stock_codes}
        total_weight = 0

        for fname, weight in factor_weights.items():
            if weight <= 0 or fname not in factors:
                continue

            factor_df = factors[fname]
            if current_idx >= len(factor_df):
                continue

            # 获取当前截面因子值
            row = factor_df.row(current_idx, named=True)
            factor_vals = {}
            for code in stock_codes:
                if code in row and row[code] is not None:
                    val = row[code]
                    if isinstance(val, (int, float)) and not np.isnan(val):
                        factor_vals[code] = float(val)

            if len(factor_vals) < 5:
                continue

            # IC 方向
            ic_dir = self._get_ic_direction(ic_df, fname, current_idx)

            # 排名
            sorted_vals = sorted(factor_vals.items(), key=lambda x: x[1])
            n = len(sorted_vals)
            for rank_idx, (code, _) in enumerate(sorted_vals):
                pct_rank = (rank_idx + 1) / n
                if ic_dir < 0:
                    pct_rank = 1 - pct_rank
                scores[code] += pct_rank * weight

            total_weight += weight

        if total_weight == 0:
            return None

        # 归一化
        scores = {k: v / total_weight for k, v in scores.items()}
        scores = {k: v for k, v in scores.items() if v > 0}

        if not scores:
            return None

        # 3. 取 Top-N
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = sorted_scores[: self.top_n]

        # 按分数加权
        total_score = sum(s for _, s in top_stocks)
        if total_score <= 0:
            # 退化为等权
            weights = {code: 1.0 / len(top_stocks) for code, _ in top_stocks}
        else:
            weights = {code: s / total_score for code, s in top_stocks}

        # 4. 应用权重上限
        weights = self.apply_weight_cap(weights)
        return weights

    def select_strong_factors(
        self,
        ic_df: pl.DataFrame,
        train_end: str,
    ) -> list[str]:
        """筛选强因子：IC 绝对值和 ICIR 达标"""
        return FactorOptimizer.select_strong_factors(
            ic_df, train_end,
            min_ic=self.config.get("min_ic", 0.02),
            min_icir=self.config.get("min_ic_ir", 0.1),
            corr_threshold=self.config.get("factor_corr_threshold", 0.85),
        )

    @staticmethod
    def _get_ic_direction(ic_df: pl.DataFrame, factor_name: str, current_idx: int) -> float:
        """获取因子 IC 方向"""
        if factor_name not in ic_df.columns:
            return 1.0
        lookback = min(60, current_idx)
        if lookback < 5:
            return 1.0
        recent_ic = ic_df[factor_name][max(0, current_idx - lookback) : current_idx].drop_nulls()
        if len(recent_ic) == 0:
            return 1.0
        return float(recent_ic.mean())


__all__ = ["ICIRSelector"]
