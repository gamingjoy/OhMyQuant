"""反转因子

基于短期反转效应，近期下跌的股票未来可能反弹。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor
from .momentum import _pct_change


@register_factor("rev_5d", category="reversal")
class Reversal5D(Factor):
    """5日反转因子（反向）"""

    name = "rev_5d"
    category = "reversal"
    description = "5日反转（近期收益的反向）"
    direction = -1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 5)


@register_factor("rev_10d", category="reversal")
class Reversal10D(Factor):
    """10日反转因子"""

    name = "rev_10d"
    category = "reversal"
    description = "10日反转"
    direction = -1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 10)


@register_factor("rev_20d", category="reversal")
class Reversal20D(Factor):
    """20日反转因子"""

    name = "rev_20d"
    category = "reversal"
    description = "20日反转"
    direction = -1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 20)


__all__ = ["Reversal5D", "Reversal10D", "Reversal20D"]
