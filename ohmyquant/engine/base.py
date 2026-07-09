"""回测引擎基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import polars as pl

from ..core.config_models import StrategyConfig
from ..core.types import WeightMap


@dataclass
class BacktestResult:
    """回测结果"""

    nav: pl.Series  # 净值序列
    dates: list[str]  # 日期列表
    strategy_name: str = ""
    strategy_version: str = ""

    # 持仓日志
    stock_weights_by_date: dict[str, dict[str, float]] = field(default_factory=dict)
    pool_weight_log: list[dict] = field(default_factory=list)
    exposure_log: list[dict] = field(default_factory=list)

    # 收益分解
    daily_returns: pl.Series | None = None
    benchmark_nav: pl.Series | None = None
    benchmark_dates: list[str] | None = None

    # 配置快照
    config: StrategyConfig | None = None

    @property
    def final_nav(self) -> float:
        return float(self.nav[-1]) if len(self.nav) > 0 else 1.0

    @property
    def n_days(self) -> int:
        return len(self.dates)


class BaseEngine(ABC):
    """回测引擎抽象基类"""

    @abstractmethod
    def run(
        self,
        pools: dict[str, list[str]] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> BacktestResult:
        """运行回测"""
        ...


__all__ = ["BacktestResult", "BaseEngine"]
