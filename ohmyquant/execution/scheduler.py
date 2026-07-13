"""调仓调度器

可插拔调度接口，支持日历频率和自适应频率。

配置中通过 rebalance.frequency 切换:
  frequency: daily / weekly / monthly / quarterly → CalendarScheduler
  frequency: adaptive                             → AdaptiveScheduler（日历 + 波动率触发）

CalendarScheduler 委托给 BaseAllocator.get_rebalance_dates() 的现有逻辑，
确保调仓日计算结果与 Phase 4 一致。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import polars as pl

from ..core.logging import get_logger
from ..core.plugin_system import register_scheduler
from ..engine.allocator import BaseAllocator

logger = get_logger(__name__)

TRADING_DAYS = 242


class BaseScheduler(ABC):
    """调仓调度器抽象基类

    子类实现 get_rebalance_dates() 方法，根据日期列表计算调仓日集合。
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.frequency: str = cfg.get("frequency", "monthly")
        self.weekday: int = cfg.get("weekday", 0)

    @abstractmethod
    def get_rebalance_dates(self, dates: list[str], **kwargs) -> set[str]:
        """计算调仓日

        Args:
            dates: 日期列表（"YYYY-MM-DD" 格式字符串）
            **kwargs: 额外参数（如 daily_returns 供 AdaptiveScheduler 使用）

        Returns:
            调仓日集合
        """
        ...


@register_scheduler("calendar")
class CalendarScheduler(BaseScheduler):
    """日历调度器

    委托给 BaseAllocator.get_rebalance_dates() 的现有逻辑。
    支持 daily / weekly / monthly / quarterly 频率。
    """

    def get_rebalance_dates(self, dates: list[str], **kwargs) -> set[str]:
        return BaseAllocator.get_rebalance_dates(
            dates, self.frequency, self.weekday
        )


@register_scheduler("adaptive")
class AdaptiveScheduler(BaseScheduler):
    """自适应调度器

    日历频率 + 波动率触发：
    1. 先计算基础日历调仓日（按 frequency）
    2. 检查近期年化波动率是否超过阈值
    3. 若超过且距上次调仓 >= min_rebalance_interval 天，追加调仓日

    当 daily_returns 为 None 时退化为 CalendarScheduler 行为。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = config or {}
        self.vol_threshold: float = cfg.get("vol_threshold", 0.3)
        self.lookback: int = cfg.get("lookback", 20)
        self.min_rebalance_interval: int = cfg.get("min_rebalance_interval", 5)

    def get_rebalance_dates(
        self, dates: list[str], daily_returns: pl.Series | None = None, **kwargs
    ) -> set[str]:
        # 基础日历调仓日
        base_dates = BaseAllocator.get_rebalance_dates(
            dates, self.frequency, self.weekday
        )

        # 无日收益数据，退化为日历逻辑
        if daily_returns is None or len(daily_returns) == 0:
            return base_dates

        # 波动率触发的额外调仓日
        adaptive_dates = self._compute_vol_triggered_dates(dates, daily_returns)

        # 合并（集合并集）
        return base_dates | adaptive_dates

    def _compute_vol_triggered_dates(
        self, dates: list[str], daily_returns: pl.Series
    ) -> set[str]:
        """计算波动率触发的额外调仓日"""
        ret_arr = daily_returns.to_numpy()
        adaptive_dates: set[str] = set()
        last_rebal_idx = -self.min_rebalance_interval - 1  # 确保首次能触发

        for i in range(len(dates)):
            # 距上次调仓不足间隔，跳过
            if i - last_rebal_idx < self.min_rebalance_interval:
                continue

            # 数据不足，跳过
            if i < self.lookback:
                continue

            # 计算近期年化波动率
            start = max(0, i - self.lookback)
            window = ret_arr[start:i]
            if len(window) < 10:
                continue

            current_vol = float(np.std(window, ddof=1)) * np.sqrt(TRADING_DAYS)

            if current_vol > self.vol_threshold:
                adaptive_dates.add(dates[i])
                last_rebal_idx = i

        return adaptive_dates


def create_scheduler(config: dict | None = None) -> BaseScheduler:
    """工厂方法：根据配置创建调度器

    Args:
        config: 调度配置 dict，frequency == "adaptive" 创建 AdaptiveScheduler，
                否则创建 CalendarScheduler

    Returns:
        BaseScheduler 实例
    """
    from ..core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    frequency = cfg.get("frequency", "monthly")
    name = "adaptive" if frequency == "adaptive" else "calendar"
    return PluginRegistry.create(PluginType.SCHEDULER, name, config=cfg)


__all__ = [
    "BaseScheduler",
    "CalendarScheduler",
    "AdaptiveScheduler",
    "create_scheduler",
]
