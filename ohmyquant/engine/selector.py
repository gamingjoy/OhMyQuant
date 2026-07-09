"""选股器基类

可插拔选股接口，参考 halo_index 的 BaseSelector。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import polars as pl


class BaseSelector(ABC):
    """选股器抽象基类

    子类实现 select() 方法，根据因子值和 IC 数据选出股票并分配权重。

    配置中通过 selection.method 切换:
      method: icir    → ICIRSelector
      method: ml      → MLSelector
      method: hybrid  → HybridSelector
      method: adaptive → AdaptiveICIRSelector
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.top_n: int = self.config.get("top_n", 10)
        self.max_stock_weight: float = self.config.get("max_stock_weight", 0.025)
        self.ic_decay: float = self.config.get("ic_decay", 0.65)
        self.icir_window: int = self.config.get("icir_window", 60)

    @abstractmethod
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
        """选股

        Args:
            factors: {factor_name: date×code 宽表}
            ic_df: IC 数据
            stock_codes: 候选股票代码
            current_idx: 当前时间索引
            close: 收盘价宽表
            regime: 市场状态
            strong_factors: 强因子列表

        Returns:
            {code: weight} 或 None
        """
        ...

    @abstractmethod
    def select_strong_factors(
        self,
        ic_df: pl.DataFrame,
        train_end: str,
    ) -> list[str]:
        """筛选强因子"""
        ...

    def apply_weight_cap(
        self, weights: dict[str, float], cap: float | None = None
    ) -> dict[str, float]:
        """应用个股权重上限"""
        cap = cap or self.max_stock_weight
        if not weights:
            return weights

        # 迭代截断
        for _ in range(10):
            capped = {k: min(v, cap) for k, v in weights.items()}
            excess = sum(v - cap for v in weights.values() if v > cap)
            if excess < 1e-8:
                break
            # 将超出部分按比例分配给未超限的
            under_cap = {k: v for k, v in capped.items() if v < cap}
            total_under = sum(under_cap.values())
            if total_under > 0:
                for k in under_cap:
                    capped[k] += excess * (under_cap[k] / total_under)
            weights = capped

        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        return weights


__all__ = ["BaseSelector"]
