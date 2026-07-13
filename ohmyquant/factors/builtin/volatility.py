"""波动率因子

基于历史波动率，低波动效应。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor


def _daily_returns(close: pl.DataFrame) -> pl.DataFrame:
    """计算日收益率"""
    date_col = close["date"]
    numeric = close.drop("date")
    returns = numeric / numeric.shift(1) - 1
    return returns.insert_column(0, date_col)


@register_factor("vol_20d", category="volatility")
class Volatility20D(Factor):
    """20日波动率"""

    name = "vol_20d"
    category = "volatility"
    description = "20日日收益率标准差"
    direction = -1  # 低波动因子
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        returns = _daily_returns(data["close"])
        date_col = returns["date"]
        numeric = returns.drop("date")
        result = numeric.select(pl.all().rolling_std(window_size=20))
        return result.insert_column(0, date_col)


@register_factor("vol_60d", category="volatility")
class Volatility60D(Factor):
    """60日波动率"""

    name = "vol_60d"
    category = "volatility"
    description = "60日日收益率标准差"
    direction = -1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        returns = _daily_returns(data["close"])
        date_col = returns["date"]
        numeric = returns.drop("date")
        result = numeric.select(pl.all().rolling_std(window_size=60))
        return result.insert_column(0, date_col)


@register_factor("vol_120d", category="volatility")
class Volatility120D(Factor):
    """120日波动率"""

    name = "vol_120d"
    category = "volatility"
    description = "120日日收益率标准差"
    direction = -1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        returns = _daily_returns(data["close"])
        date_col = returns["date"]
        numeric = returns.drop("date")
        result = numeric.select(pl.all().rolling_std(window_size=120))
        return result.insert_column(0, date_col)


@register_factor("amihud_illiq", category="volatility")
class AmihudIlliquidity(Factor):
    """Amihud 非流动性因子

    |收益率| / 成交额 的均值，衡量流动性。
    """

    name = "amihud_illiq"
    category = "volatility"
    description = "Amihud非流动性（|收益|/金额）"
    direction = -1
    required_fields = ["close", "money"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        money = data["money"]
        date_col = close["date"]

        close_num = close.drop("date")
        money_num = money.drop("date")
        returns = (close_num / close_num.shift(1) - 1).select(pl.all().abs())
        # 避免除零
        illiq = returns / (money_num + 1e-8)
        result = illiq.select(pl.all().rolling_mean(window_size=20))
        return result.insert_column(0, date_col)


__all__ = ["Volatility20D", "Volatility60D", "Volatility120D", "AmihudIlliquidity"]
