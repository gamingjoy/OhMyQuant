"""ICIR 加权分配器

基于各池强因子 ICIR 加权的池间分配。
泛化 halo_index 的 compute_pool_ic_ir_weights 到 N 池。

对每个池，计算其强因子的平均 ICIR，按 ICIR 比例分配权重。
支持与 HRP 混合（weight_blend 参数控制混合比例）。
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_allocator
from ..allocator import BaseAllocator
from .hrp_allocator import HRPAllocator

logger = get_logger(__name__)


@register_allocator("icir_weighted")
class ICIRWeightedAllocator(BaseAllocator):
    """ICIR 加权分配器

    根据各池因子的预测能力（ICIR）动态分配权重。
    ICIR 高的池获得更多权重。

    可选与 HRP 混合（weight_blend 控制）:
      final_weight = (1 - weight_blend) * hrp_weight + weight_blend * icir_weight
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # 内部 HRP 分配器用于混合
        self._hrp = HRPAllocator(config)
        self.ic_decay: float = self.config_get(config, "ic_decay", 0.80)
        self.rolling_window: int = self.config_get(config, "rolling_window", 120)
        self.min_weight: float = self.config_get(config, "min_pool_weight", 0.2)
        self.max_weight: float = self.config_get(config, "max_pool_weight", 0.8)

    @staticmethod
    def config_get(cfg: dict, key: str, default):
        return cfg.get(key, default) if cfg else default

    def allocate(
        self,
        pool_returns: dict[str, pl.Series],
        current_idx: int,
        prev_weights: dict[str, float],
        regime: str | None = None,
        **kwargs,
    ) -> dict[str, float]:
        pool_names = list(pool_returns.keys())
        n = len(pool_names)
        if n == 0:
            return {}
        if n == 1:
            return {pool_names[0]: 1.0}

        # 1. HRP 权重
        hrp_weights = self._hrp.allocate(
            pool_returns, current_idx, prev_weights, regime
        )

        # 2. ICIR 权重（需要 pool_ic_df 和 pool_strong_factors）
        pool_ic_df = kwargs.get("pool_ic_df", {})
        pool_strong_factors = kwargs.get("pool_strong_factors", {})

        if not pool_ic_df or not pool_strong_factors or current_idx < self.rolling_window:
            # ICIR 数据不足，退化为 HRP
            return hrp_weights

        icir_weights = self._compute_icir_weights(
            pool_ic_df, pool_strong_factors, pool_names, current_idx
        )

        # 3. 混合
        final_weights = {}
        for p in pool_names:
            hrp_w = hrp_weights.get(p, 1.0 / n)
            icir_w = icir_weights.get(p, 1.0 / n)
            final_weights[p] = (1 - self.weight_blend) * hrp_w + self.weight_blend * icir_w

        # 4. 归一化 + clip
        total = sum(final_weights.values())
        if total > 0:
            final_weights = {k: v / total for k, v in final_weights.items()}

        # 防止过度集中
        final_weights = self._clip_weights(final_weights)

        return final_weights

    def _compute_icir_weights(
        self,
        pool_ic_df: dict[str, pl.DataFrame],
        pool_strong_factors: dict[str, list[str]],
        pool_names: list[str],
        current_idx: int,
    ) -> dict[str, float]:
        """计算各池的 ICIR 权重

        Args:
            pool_ic_df: {pool_name: ic_df} 各池的 IC 数据
            pool_strong_factors: {pool_name: [factor_name, ...]}
            pool_names: 池名列表
            current_idx: 当前时间索引

        Returns:
            {pool_name: weight}
        """
        window_start = max(0, current_idx - self.rolling_window)

        pool_icir: dict[str, float] = {}
        for pool in pool_names:
            ic_df = pool_ic_df.get(pool)
            if ic_df is None:
                pool_icir[pool] = 0.0
                continue

            strong = pool_strong_factors.get(pool, [])
            ic_slice = ic_df[window_start:current_idx]

            ic_sum, count = 0.0, 0
            for factor in strong:
                if factor not in ic_slice.columns:
                    continue
                ic_vals = ic_slice[factor].drop_nulls().to_numpy()
                if len(ic_vals) < 20:
                    continue

                # 指数衰减加权
                if self.ic_decay < 1.0 and len(ic_vals) > 5:
                    w = np.array([self.ic_decay ** k for k in range(len(ic_vals))])[::-1]
                    w = w / w.sum()
                    ic_mean = float(np.average(ic_vals, weights=w))
                    ic_std = float(np.sqrt(np.average((ic_vals - ic_mean) ** 2, weights=w)))
                else:
                    ic_mean = float(np.mean(ic_vals))
                    ic_std = float(np.std(ic_vals))

                if ic_std > 0:
                    ic_sum += max(ic_mean / ic_std, 0)
                count += 1

            pool_icir[pool] = ic_sum / count if count > 0 else 0.0

        # 按 ICIR 比例分配
        total_icir = sum(pool_icir.values())
        if total_icir > 0:
            return {p: pool_icir[p] / total_icir for p in pool_names}

        # 全部 ICIR 为 0，退化为等权
        weight = 1.0 / len(pool_names)
        return {p: weight for p in pool_names}

    def _clip_weights(self, weights: dict[str, float]) -> dict[str, float]:
        """权重截断到 [min_weight, max_weight] 并归一化"""
        n = len(weights)
        if n == 0:
            return weights

        # 自适应：根据池数调整上下限
        effective_min = min(self.min_weight, 1.0 / n)
        effective_max = max(self.max_weight, 1.0 / n)

        clipped = {k: float(np.clip(v, effective_min, effective_max)) for k, v in weights.items()}

        # 归一化
        total = sum(clipped.values())
        if total > 0:
            clipped = {k: v / total for k, v in clipped.items()}

        return clipped


__all__ = ["ICIRWeightedAllocator"]
