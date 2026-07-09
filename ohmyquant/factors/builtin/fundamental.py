"""基本面因子

基于估值数据的因子，需要 BacktestEngine 加载 valuation 数据。
required_fields 对应 DataCatalog.get_valuation() 返回的列名。

数据加载: BacktestEngine._load_pool_data 已增强，自动加载 pe_ratio/pb_ratio 等字段。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor


def _invert(df: pl.DataFrame) -> pl.DataFrame:
    """取倒数（1/x），处理 0 值"""
    date_col = df["date"]
    numeric = df.drop("date")
    inverted = numeric.select(
        [
            pl.when(pl.col(c).abs() > 1e-8)
            .then(1.0 / pl.col(c))
            .otherwise(None)
            .alias(c)
            for c in numeric.columns
        ]
    )
    return inverted.insert_column(0, date_col)


def _log_transform(df: pl.DataFrame) -> pl.DataFrame:
    """对数变换"""
    date_col = df["date"]
    numeric = df.drop("date")
    logged = numeric.select(
        [
            pl.when(pl.col(c) > 0)
            .then(pl.col(c).log())
            .otherwise(None)
            .alias(c)
            for c in numeric.columns
        ]
    )
    return logged.insert_column(0, date_col)


@register_factor("ep_ratio", category="fundamental")
class EPRatio(Factor):
    """盈利收益率（E/P = 1/PE）"""

    name = "ep_ratio"
    category = "fundamental"
    description = "盈利收益率 = 1/PE，值越大越便宜"
    direction = 1
    required_fields = ["pe_ratio"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _invert(data["pe_ratio"])


@register_factor("bp_ratio", category="fundamental")
class BPRatio(Factor):
    """账面价值比（B/P = 1/PB）"""

    name = "bp_ratio"
    category = "fundamental"
    description = "账面价值比 = 1/PB，值越大越便宜"
    direction = 1
    required_fields = ["pb_ratio"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _invert(data["pb_ratio"])


@register_factor("sp_ratio", category="fundamental")
class SPRatio(Factor):
    """市销率倒数（S/P = 1/PS）"""

    name = "sp_ratio"
    category = "fundamental"
    description = "市销率倒数 = 1/PS，值越大越便宜"
    direction = 1
    required_fields = ["ps_ratio"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _invert(data["ps_ratio"])


@register_factor("turnover_ratio", category="fundamental")
class TurnoverRatio(Factor):
    """换手率因子（低换手率溢价）"""

    name = "turnover_ratio"
    category = "fundamental"
    description = "换手率，值越低预期收益越高（流动性溢价）"
    direction = -1
    required_fields = ["turnover_ratio"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return data["turnover_ratio"]


@register_factor("log_market_cap", category="fundamental")
class LogMarketCap(Factor):
    """对数市值因子（小市值溢价）"""

    name = "log_market_cap"
    category = "fundamental"
    description = "对数总市值，值越小预期收益越高（小盘溢价）"
    direction = -1
    required_fields = ["market_cap"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return _log_transform(data["market_cap"])


@register_factor("dividend_yield", category="fundamental")
class DividendYield(Factor):
    """股息率因子"""

    name = "dividend_yield"
    category = "fundamental"
    description = "股息率，值越高预期收益越高"
    direction = 1
    required_fields = ["dividend_ratio"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        return data["dividend_ratio"]


__all__ = [
    "EPRatio",
    "BPRatio",
    "SPRatio",
    "TurnoverRatio",
    "LogMarketCap",
    "DividendYield",
]
