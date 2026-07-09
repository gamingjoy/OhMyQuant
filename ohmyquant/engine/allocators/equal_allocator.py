"""等权分配器

所有池等权重分配，最简单的基线方案。
"""
from __future__ import annotations

import polars as pl

from ...core.plugin_system import register_allocator
from ..allocator import BaseAllocator


@register_allocator("equal")
class EqualAllocator(BaseAllocator):
    """等权分配器

    所有池获得相同权重 1/N。
    适合作为基线对比或不知道哪个池更优时使用。
    """

    def allocate(
        self,
        pool_returns: dict[str, pl.Series],
        current_idx: int,
        prev_weights: dict[str, float],
        regime: str | None = None,
        **kwargs,
    ) -> dict[str, float]:
        n = len(pool_returns)
        if n == 0:
            return {}
        weight = 1.0 / n
        return {pool: weight for pool in pool_returns}


__all__ = ["EqualAllocator"]
