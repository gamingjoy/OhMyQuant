"""动量轮动选股器

不依赖 IC/ICIR 筛选，直接按因子值排名选股。
适用于 ETF 等小池场景（IC 统计不稳健时使用）。

selection:
  method: momentum        # 使用此选股器
  top_n: 3                # 选 Top-3
  max_stock_weight: 0.34  # 单标的权重上限
  factor_weighting: equal # equal | ic_weighted（equal=等权平均）
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ..selector import BaseSelector

logger = get_logger(__name__)


@register_selector("momentum")
class MomentumSelector(BaseSelector):
    """动量轮动选股器

    流程:
      1. 对每个因子，取当前截面值并排名（百分位）
      2. 等权平均各因子的百分位排名 → 综合得分
      3. 取 Top-N，等权或按分数加权
      4. 应用个股权重上限

    与 ICIRSelector 的区别:
      - 不依赖 IC/ICIR 筛选强因子（小池 IC 不稳健）
      - 直接用因子值排名，假设动量因子方向为正
      - 适用于 ETF 轮动、小池策略
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.factor_weighting: str = self.config.get("factor_weighting", "equal")

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
        factor_names = strong_factors or list(factors.keys())
        if not factor_names:
            return None

        scores: dict[str, float] = {code: 0.0 for code in stock_codes}
        n_factors_used = 0

        for fname in factor_names:
            if fname not in factors:
                continue

            factor_df = factors[fname]
            if current_idx >= len(factor_df):
                continue

            row = factor_df.row(current_idx, named=True)
            factor_vals: dict[str, float] = {}
            for code in stock_codes:
                if code in row and row[code] is not None:
                    val = row[code]
                    if isinstance(val, (int, float)) and not np.isnan(val):
                        factor_vals[code] = float(val)

            if len(factor_vals) < 2:
                continue

            # 百分位排名（0~1，值越大排名越高）
            sorted_vals = sorted(factor_vals.items(), key=lambda x: x[1])
            n = len(sorted_vals)
            for rank_idx, (code, _) in enumerate(sorted_vals):
                pct_rank = (rank_idx + 1) / n
                scores[code] += pct_rank

            n_factors_used += 1

        if n_factors_used == 0:
            return None

        # 等权平均
        scores = {k: v / n_factors_used for k, v in scores.items()}
        scores = {k: v for k, v in scores.items() if v > 0}

        if not scores:
            return None

        # 取 Top-N
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = sorted_scores[: self.top_n]

        # 等权分配
        weights = {code: 1.0 / len(top_stocks) for code, _ in top_stocks}

        # 应用权重上限
        weights = self.apply_weight_cap(weights)
        return weights

    def select_strong_factors(
        self,
        ic_df: pl.DataFrame,
        train_end: str,
    ) -> list[str]:
        """返回所有因子（不做 IC 筛选）"""
        factor_cols = [c for c in ic_df.columns if c != "date"]
        logger.info(f"动量选股器: 跳过 IC 筛选，使用全部 {len(factor_cols)} 个因子")
        return factor_cols


__all__ = ["MomentumSelector"]
