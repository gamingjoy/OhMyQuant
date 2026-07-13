"""HRP 分层风险平价分配器

基于各池收益协方差的分层风险平价分配。
泛化 halo_index 的 compute_pool_hrp_weights 到 N 池。

对于 2 池：使用解析解 alpha = 1 - V0/(V0+V1-2*sqrt(V0*V1)*corr)
对于 N>2 池：使用 inverse-variance weighting（反方差加权）
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_allocator
from ..allocator import BaseAllocator
from ..risk import REGIME_HIGH_VOL, REGIME_SIDEWAY, TRADING_DAYS

logger = get_logger(__name__)


@register_allocator("hrp")
class HRPAllocator(BaseAllocator):
    """HRP 分层风险平价分配器

    根据各池历史收益的协方差结构分配权重。
    波动率低的池获得更高权重。
    """

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

        lookback_start = max(0, current_idx - self.lookback)

        # 提取各池收益切片
        pool_hist = {}
        for name in pool_names:
            rets = pool_returns[name].to_numpy()[lookback_start:current_idx]
            if len(rets) < 20:
                # 数据不足，退化为等权
                weight = 1.0 / n
                return {p: weight for p in pool_names}
            pool_hist[name] = rets

        # 构建收益矩阵
        ret_matrix = np.column_stack([pool_hist[name] for name in pool_names])

        if n == 2:
            weights = self._compute_two_pool_weights(ret_matrix, pool_names)
        else:
            weights = self._compute_n_pool_weights(ret_matrix, pool_names)

        # Regime 调整：高波动/震荡市更偏向反方差
        if regime in (REGIME_SIDEWAY, REGIME_HIGH_VOL):
            inv_var_weights = self._inverse_variance_weights(ret_matrix, pool_names)
            blend = 0.5 if regime == REGIME_SIDEWAY else 0.7
            for p in pool_names:
                weights[p] = (1 - blend) * weights[p] + blend * inv_var_weights[p]

        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _compute_two_pool_weights(
        self, ret_matrix: np.ndarray, pool_names: list[str]
    ) -> dict[str, float]:
        """2 池 HRP 解析解（移植 halo_index）"""
        cov = np.cov(ret_matrix, rowvar=False)
        v0, v1 = cov[0, 0], cov[1, 1]
        corr = np.corrcoef(ret_matrix, rowvar=False)[0, 1]

        if v0 > 0 and v1 > 0 and abs(corr) < 1:
            alpha = 1 - v0 / (v0 + v1 - 2 * np.sqrt(v0 * v1) * corr)
            alpha = float(np.clip(alpha, 0.1, 0.9))
        else:
            alpha = 0.5

        return {pool_names[0]: alpha, pool_names[1]: 1 - alpha}

    def _compute_n_pool_weights(
        self, ret_matrix: np.ndarray, pool_names: list[str]
    ) -> dict[str, float]:
        """N 池反方差加权"""
        return self._inverse_variance_weights(ret_matrix, pool_names)

    @staticmethod
    def _inverse_variance_weights(
        ret_matrix: np.ndarray, pool_names: list[str]
    ) -> dict[str, float]:
        """反方差加权：vol 越低权重越高"""
        variances = np.var(ret_matrix, axis=0, ddof=1)
        inv_var = 1.0 / np.maximum(variances, 1e-10)
        weights = inv_var / inv_var.sum()
        return {name: float(w) for name, w in zip(pool_names, weights)}


__all__ = ["HRPAllocator"]
