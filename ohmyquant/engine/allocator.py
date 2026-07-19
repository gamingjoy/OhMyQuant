"""池间分配器基类

可插拔分配器接口，支持 N 池架构。
参考 halo_index 的 PoolAllocator，泛化到任意数量池。

配置中通过 allocation.method 切换:
  method: equal → EqualAllocator（等权）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


class BaseAllocator(ABC):
    """池间分配器抽象基类

    子类实现 allocate() 方法，根据各池历史收益计算各池权重。

    N 池架构：不局限于 2 池，支持任意数量池。
    权重格式：dict[str, float]，{pool_name: weight}，权重和为 1.0。
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.lookback: int = cfg.get("lookback", 60)
        self.weight_change_limit: float = cfg.get("weight_change_limit", 0.10)
        self.weight_blend: float = cfg.get("weight_blend", 0.25)

    @abstractmethod
    def allocate(
        self,
        pool_returns: dict[str, pl.Series],
        current_idx: int,
        prev_weights: dict[str, float],
        regime: str | None = None,
        **kwargs,
    ) -> dict[str, float]:
        """计算各池权重

        Args:
            pool_returns: {pool_name: daily_return_series} 各池日收益序列
            current_idx: 当前时间索引
            prev_weights: 前一次调仓的池权重 {pool_name: weight}
            regime: 当前市场状态（可选）
            **kwargs: 额外参数（如 ic_df, strong_factors 供 ICIRWeightedAllocator 使用）

        Returns:
            {pool_name: weight}，权重和为 1.0
        """
        ...

    def smooth_weights(
        self,
        new_weights: dict[str, float],
        prev_weights: dict[str, float],
    ) -> dict[str, float]:
        """权重平滑：变化过大时混合新旧权重

        当总变化超过 weight_change_limit 时，按 weight_blend 比例混合新旧权重。
        """
        all_pools = set(new_weights) | set(prev_weights)
        delta = sum(
            abs(new_weights.get(k, 0) - prev_weights.get(k, 0)) for k in all_pools
        )

        if delta > self.weight_change_limit and prev_weights:
            blended = {}
            for k in new_weights:
                blended[k] = (
                    self.weight_blend * new_weights[k]
                    + (1 - self.weight_blend) * prev_weights.get(k, 0)
                )
            total = sum(blended.values())
            if total > 0:
                return {k: v / total for k, v in blended.items()}
            return new_weights
        return new_weights

    @staticmethod
    def get_rebalance_dates(
        dates: list,
        freq: str = "monthly",
        weekday: int = 0,
    ) -> set:
        """根据频率计算调仓日

        Args:
            dates: 日期列表（"YYYY-MM-DD" 格式字符串 或 datetime.date 对象）
            freq: 调仓频率 daily / weekly / biweekly / monthly / quarterly
            weekday: 周频率时的星期几（0=周一 ... 4=周五）

        Returns:
            调仓日集合（与输入类型一致）
        """
        if not dates:
            return set()

        if freq == "daily":
            return set(dates)

        rebal_dates: set = set()
        prev_key = None
        # weekly/biweekly 共用：本周首个交易日（兜底用）+ 是否已命中目标weekday
        week_pending = None
        week_done = False
        # biweekly 隔周调仓：触发周内命中 weekday 调仓，无 weekday 时取首日兜底
        biweekly_trigger = False

        for date_item in dates:
            # 转换为 datetime 对象
            if isinstance(date_item, str):
                try:
                    dt = datetime.strptime(date_item, "%Y-%m-%d")
                except ValueError:
                    continue
            else:
                # datetime.date 或 datetime.datetime 对象
                dt = date_item

            if freq == "weekly":
                key = (dt.isocalendar()[0], dt.isocalendar()[1])
                if key != prev_key:
                    # 新的一周：提交上周的兜底（若未命中 weekday）
                    if not week_done and week_pending is not None:
                        rebal_dates.add(week_pending)
                    week_pending = None
                    week_done = False
                    prev_key = key
                if not week_done:
                    if dt.weekday() == weekday:
                        # 命中目标 weekday → 调仓
                        rebal_dates.add(date_item)
                        week_done = True
                        week_pending = None
                    elif week_pending is None:
                        # 记录本周首个交易日作为兜底（目标 weekday 是假期时使用）
                        week_pending = date_item
            elif freq == "biweekly":
                # 隔周调仓：每两周的指定 weekday 调仓一次
                iso = dt.isocalendar()
                key = (iso[0], iso[1])
                if key != prev_key:
                    # 新的一周：先提交上一触发周的兜底日期（若未命中 weekday）
                    if (
                        biweekly_trigger
                        and not week_done
                        and week_pending is not None
                    ):
                        rebal_dates.add(week_pending)
                    week_pending = None
                    week_done = False
                    # 翻转触发标志
                    biweekly_trigger = not biweekly_trigger
                    prev_key = key
                if biweekly_trigger and not week_done:
                    if dt.weekday() == weekday:
                        rebal_dates.add(date_item)
                        week_done = True
                        week_pending = None
                    elif week_pending is None:
                        # 记录本周首个交易日作为兜底
                        week_pending = date_item
            elif freq == "monthly":
                key = (dt.year, dt.month)
                if key != prev_key:
                    rebal_dates.add(date_item)
                    prev_key = key
            elif freq == "quarterly":
                quarter = (dt.month - 1) // 3 + 1
                key = (dt.year, quarter)
                if key != prev_key:
                    rebal_dates.add(date_item)
                    prev_key = key
            else:
                # 默认月频
                key = (dt.year, dt.month)
                if key != prev_key:
                    rebal_dates.add(date_item)
                    prev_key = key

        # 提交最后一周/最后触发周的兜底（目标 weekday 是假期时使用）
        if not week_done and week_pending is not None:
            if freq == "weekly":
                rebal_dates.add(week_pending)
            elif freq == "biweekly" and biweekly_trigger:
                rebal_dates.add(week_pending)

        return rebal_dates


__all__ = ["BaseAllocator"]
