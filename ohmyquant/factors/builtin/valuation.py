"""估值因子

基于 PE/PB/换手率等估值指标。
"""
from __future__ import annotations

import polars as pl

from ..base import Factor, register_factor


@register_factor("pe_ttm", category="valuation")
class PETTM(Factor):
    """市盈率因子"""

    name = "pe_ttm"
    category = "valuation"
    description = "市盈率（TTM）"
    direction = -1  # 低估值因子
    required_fields = ["valuation"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        if "valuation" not in data:
            return pl.DataFrame()
        val = data["valuation"]
        # valuation 是长表，需转为宽表
        if "pe_ratio" in val.columns:
            return val.pivot(values="pe_ratio", index="date", on="code").sort("date")
        return pl.DataFrame()


@register_factor("pb_ratio", category="valuation")
class PBRatio(Factor):
    """市净率因子"""

    name = "pb_ratio"
    category = "valuation"
    description = "市净率"
    direction = -1
    required_fields = ["valuation"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        if "valuation" not in data:
            return pl.DataFrame()
        val = data["valuation"]
        if "pb_ratio" in val.columns:
            return val.pivot(values="pb_ratio", index="date", on="code").sort("date")
        return pl.DataFrame()


@register_factor("ps_ratio", category="valuation")
class PSRatio(Factor):
    """市销率因子"""

    name = "ps_ratio"
    category = "valuation"
    description = "市销率"
    direction = -1
    required_fields = ["valuation"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        if "valuation" not in data:
            return pl.DataFrame()
        val = data["valuation"]
        if "ps_ratio" in val.columns:
            return val.pivot(values="ps_ratio", index="date", on="code").sort("date")
        return pl.DataFrame()


@register_factor("market_cap", category="valuation")
class MarketCap(Factor):
    """总市值因子"""

    name = "market_cap"
    category = "valuation"
    description = "总市值（对数）"
    direction = -1  # 小市值因子
    required_fields = ["market_cap"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        if "market_cap" not in data:
            return pl.DataFrame()
        wide = data["market_cap"]
        date_col = wide["date"]
        numeric = wide.drop("date")
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


__all__ = ["PETTM", "PBRatio", "PSRatio", "MarketCap"]
