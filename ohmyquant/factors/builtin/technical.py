"""技术因子

基于技术指标的因子。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor


def _rolling_mean(df: pl.DataFrame, window: int) -> pl.DataFrame:
    """对每列做 rolling mean"""
    date_col = df["date"]
    numeric = df.drop("date")
    result = numeric.select(
        [pl.col(c).rolling_mean(window_size=window).alias(c) for c in numeric.columns]
    )
    return result.insert_column(0, date_col)


def _rolling_max(df: pl.DataFrame, window: int) -> pl.DataFrame:
    date_col = df["date"]
    numeric = df.drop("date")
    result = numeric.select(
        [pl.col(c).rolling_max(window_size=window).alias(c) for c in numeric.columns]
    )
    return result.insert_column(0, date_col)


def _rolling_min(df: pl.DataFrame, window: int) -> pl.DataFrame:
    date_col = df["date"]
    numeric = df.drop("date")
    result = numeric.select(
        [pl.col(c).rolling_min(window_size=window).alias(c) for c in numeric.columns]
    )
    return result.insert_column(0, date_col)


@register_factor("rsi_14", category="technical")
class RSI14(Factor):
    """14日 RSI 相对强弱指标"""

    name = "rsi_14"
    category = "technical"
    description = "14日RSI"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        date_col = close["date"]
        numeric = close.drop("date")

        delta = numeric - numeric.shift(1)
        gain = delta.select(
            [pl.when(pl.col(c) > 0).then(pl.col(c)).otherwise(0.0).alias(c) for c in delta.columns]
        )
        loss = delta.select(
            [pl.when(pl.col(c) < 0).then(-pl.col(c)).otherwise(0.0).alias(c) for c in delta.columns]
        )

        avg_gain = gain.select(
            [pl.col(c).rolling_mean(window_size=14).alias(c) for c in gain.columns]
        )
        avg_loss = loss.select(
            [pl.col(c).rolling_mean(window_size=14).alias(c) for c in loss.columns]
        )

        rs = avg_gain / (avg_loss + 1e-8)
        rsi = rs.select(
            [(100 * pl.col(c) / (1 + pl.col(c))).alias(c) for c in rs.columns]
        )
        return rsi.insert_column(0, date_col)


@register_factor("ma_5_20_cross", category="technical")
class MA5Cross20(Factor):
    """5日均线上穿20日均线（金叉信号）"""

    name = "ma_5_20_cross"
    category = "technical"
    description = "5日/20日均线交叉信号"
    direction = 1
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        date_col = close["date"]
        numeric = close.drop("date")

        ma5 = numeric.select(
            [pl.col(c).rolling_mean(window_size=5).alias(c) for c in numeric.columns]
        )
        ma20 = numeric.select(
            [pl.col(c).rolling_mean(window_size=20).alias(c) for c in numeric.columns]
        )

        signal = (ma5 - ma20).select(
            [pl.when(pl.col(c) > 0).then(1.0).otherwise(0.0).alias(c) for c in (ma5 - ma20).columns]
        )
        return signal.insert_column(0, date_col)


@register_factor("bias_20", category="technical")
class Bias20(Factor):
    """20日乖离率（价格偏离均线的程度）"""

    name = "bias_20"
    category = "technical"
    description = "20日乖离率"
    direction = -1  # 高乖离率可能反转
    required_fields = ["close"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        date_col = close["date"]
        numeric = close.drop("date")

        ma20 = numeric.select(
            [pl.col(c).rolling_mean(window_size=20).alias(c) for c in numeric.columns]
        )
        bias = (numeric - ma20) / (ma20 + 1e-8)
        return bias.insert_column(0, date_col)


@register_factor("willr_14", category="technical")
class WilliamsR14(Factor):
    """14日威廉指标"""

    name = "willr_14"
    category = "technical"
    description = "14日威廉指标"
    direction = 1
    required_fields = ["close", "high", "low"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        high = data["high"]
        low = data["low"]
        date_col = close["date"]

        close_num = close.drop("date")
        high_num = high.drop("date")
        low_num = low.drop("date")

        hh = high_num.select(
            [pl.col(c).rolling_max(window_size=14).alias(c) for c in high_num.columns]
        )
        ll = low_num.select(
            [pl.col(c).rolling_min(window_size=14).alias(c) for c in low_num.columns]
        )

        willr = (hh - close_num) / (hh - ll + 1e-8) * -100
        return willr.insert_column(0, date_col)


__all__ = ["RSI14", "MA5Cross20", "Bias20", "WilliamsR14"]
