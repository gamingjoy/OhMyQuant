"""回测上下文

在回测过程中传递状态和数据，避免长参数列表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from ..core.types import Regime, WeightMap


@dataclass
class BacktestContext:
    """回测上下文

    封装回测过程中的状态：
      - 当前日期索引
      - 当前持仓
      - 历史净值
      - 市场状态
    """

    # 时间
    current_idx: int = 0
    current_date: str = ""
    dates: list[str] = field(default_factory=list)

    # 持仓
    current_stock_weights: WeightMap = field(default_factory=dict)
    current_pool_weights: dict[str, float] = field(default_factory=dict)

    # 净值与收益
    nav: list[float] = field(default_factory=lambda: [1.0])
    daily_returns: list[float] = field(default_factory=list)

    # 风控状态
    current_exposure: float = 1.0
    current_regime: Regime = "sideway"

    # 日志
    stock_weights_log: dict[str, WeightMap] = field(default_factory=dict)
    pool_weight_log: list[dict] = field(default_factory=list)
    exposure_log: list[dict] = field(default_factory=list)

    # 数据缓存（由引擎填充）
    data: dict[str, Any] = field(default_factory=dict)

    def update_nav(self, daily_return: float) -> None:
        """更新净值"""
        new_nav = self.nav[-1] * (1 + daily_return)
        self.nav.append(new_nav)
        self.daily_returns.append(daily_return)

    def log_state(self) -> None:
        """记录当前状态到日志"""
        self.stock_weights_log[self.current_date] = dict(self.current_stock_weights)
        self.pool_weight_log.append(
            {
                "date": self.current_date,
                "pool_weights": dict(self.current_pool_weights),
            }
        )
        self.exposure_log.append(
            {
                "date": self.current_date,
                "exposure": self.current_exposure,
                "regime": self.current_regime,
            }
        )


__all__ = ["BacktestContext"]
