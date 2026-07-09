"""动量因子

基于历史收益的动量效应。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor


def _pct_change(df: pl.DataFrame, n: int) -> pl.DataFrame:
    """计算 n 期变化率，保留 date 列"""
    date_col = df["date"]
    numeric = df.drop("date")
    shifted = numeric.shift(n)
    result = (numeric / shifted) - 1
    return result.insert_column(0, date_col)


@register_factor("mom_1m", category="momentum")
class Momentum1M(Factor):
    """1月动量因子（20日收益率）"""

    name = "mom_1m"
    category = "momentum"
    description = "1月动量（20日收益率）"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 20)


@register_factor("mom_3m", category="momentum")
class Momentum3M(Factor):
    """3月动量因子（60日收益率）"""

    name = "mom_3m"
    category = "momentum"
    description = "3月动量（60日收益率）"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 60)


@register_factor("mom_6m", category="momentum")
class Momentum6M(Factor):
    """6月动量因子（120日收益率）"""

    name = "mom_6m"
    category = "momentum"
    description = "6月动量（120日收益率）"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 120)


@register_factor("mom_12m", category="momentum")
class Momentum12M(Factor):
    """12月动量因子（240日收益率）"""

    name = "mom_12m"
    category = "momentum"
    description = "12月动量（240日收益率）"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _pct_change(data["close"], 240)


@register_factor("mom_skip_1m", category="momentum")
class MomentumSkip1M(Factor):
    """12月动量跳过最近1月（经典动量因子）"""

    name = "mom_skip_1m"
    category = "momentum"
    description = "12-1月动量（跳过最近1月的12月动量）"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        date_col = close["date"]
        numeric = close.drop("date")
        # (close[t-20] / close[t-260]) - 1
        result = (numeric.shift(20) / numeric.shift(260)) - 1
        return result.insert_column(0, date_col)


__all__ = ["Momentum1M", "Momentum3M", "Momentum6M", "Momentum12M", "MomentumSkip1M"]
