"""量价因子

基于成交量与价格关系的因子。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor
from .volatility import _daily_returns


@register_factor("turnover_20d", category="volume_price")
class Turnover20D(Factor):
    """20日平均换手率"""

    name = "turnover_20d"
    category = "volume_price"
    description = "20日平均换手率"
    direction = -1  # 低换手率因子
    required_fields = ["volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        volume = data["volume"]
        date_col = volume["date"]
        numeric = volume.drop("date")
        result = numeric.select(pl.all().rolling_mean(window_size=20))
        return result.insert_column(0, date_col)


@register_factor("volume_ratio", category="volume_price")
class VolumeRatio(Factor):
    """量比因子（当日成交量 / 20日均量）"""

    name = "volume_ratio"
    category = "volume_price"
    description = "量比（当日量/20日均量）"
    direction = 1
    required_fields = ["volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        volume = data["volume"]
        date_col = volume["date"]
        numeric = volume.drop("date")
        avg = numeric.select(pl.all().rolling_mean(window_size=20))
        result = numeric / (avg + 1e-8)
        return result.insert_column(0, date_col)


@register_factor("amount_20d", category="volume_price")
class Amount20D(Factor):
    """20日平均成交额"""

    name = "amount_20d"
    category = "volume_price"
    description = "20日平均成交额"
    direction = 1
    required_fields = ["money"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        money = data["money"]
        date_col = money["date"]
        numeric = money.drop("date")
        result = numeric.select(pl.all().rolling_mean(window_size=20))
        return result.insert_column(0, date_col)


@register_factor("price_volume_corr", category="volume_price")
class PriceVolumeCorrelation(Factor):
    """量价相关系数（20日滚动）"""

    name = "price_volume_corr"
    category = "volume_price"
    description = "20日收益率与成交量变化的相关系数"
    direction = 1
    required_fields = ["close", "volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        volume = data["volume"]
        date_col = close["date"]

        close_num = close.drop("date")
        vol_num = volume.drop("date")
        ret = close_num / close_num.shift(1) - 1
        vol_chg = vol_num / vol_num.shift(1) - 1

        # 滚动相关系数（简化：用乘积均值近似）
        product = ret * vol_chg
        result = product.select(pl.all().rolling_mean(window_size=20))
        return result.insert_column(0, date_col)


@register_factor("obv_slope", category="volume_price")
class OBVSlope(Factor):
    """OBV 斜率因子

    OBV（能量潮）的20日线性回归斜率。
    """

    name = "obv_slope"
    category = "volume_price"
    description = "OBV20日斜率"
    direction = 1
    required_fields = ["close", "volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        volume = data["volume"]
        date_col = close["date"]

        close_num = close.drop("date")
        vol_num = volume.drop("date")

        # 上涨日加量，下跌日减量
        ret_sign = (close_num - close_num.shift(1)).select(pl.all().sign())
        signed_vol = vol_num * ret_sign
        obv = signed_vol.select(pl.all().cum_sum())

        # 20日斜率近似：(OBV[t] - OBV[t-20]) / 20
        result = (obv - obv.shift(20)) / 20
        return result.insert_column(0, date_col)


__all__ = [
    "Turnover20D",
    "VolumeRatio",
    "Amount20D",
    "PriceVolumeCorrelation",
    "OBVSlope",
]
