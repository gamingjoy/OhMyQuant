"""宽表构建器

将原始数据（行情/估值/融资融券/资金流/行业）JOIN 为宽表，
按年份分区存储为 Parquet。

兼容 download_a_share 的 db_manager.py 设计。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from ...core.logging import get_logger

logger = get_logger(__name__)


class WideTableBuilder:
    """宽表构建器

    将多个原始 Parquet 表 JOIN 为一张宽表，按年份分区存储。

    用法:
        builder = WideTableBuilder("D:/Work/Project/download_a_share/data")
        builder.build_stock_wide_table(rebuild_all_years=False)
    """

    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.parquet_root = self.data_root / "parquet"

    def build_stock_wide_table(self, rebuild_all_years: bool = False) -> None:
        """构建股票宽表

        Args:
            rebuild_all_years: True 重建所有年份，False 只重建当年
        """
        if rebuild_all_years:
            years = self._list_years("stock_daily_price")
        else:
            years = [str(datetime.now().year)]

        output_dir = self.data_root / "stock_daily_wide_partitioned"

        for year in years:
            logger.info(f"构建股票宽表: {year}")
            df = self._join_stock_tables(year)
            if df is not None and not df.is_empty():
                year_dir = output_dir / f"year={year}"
                year_dir.mkdir(parents=True, exist_ok=True)
                df.write_parquet(year_dir / "data.parquet")
                logger.info(f"  写入 {len(df)} 行 -> {year_dir}")

    def build_etf_wide_table(self, rebuild_all_years: bool = False) -> None:
        """构建 ETF 宽表"""
        if rebuild_all_years:
            years = self._list_years("etf_daily_price")
        else:
            years = [str(datetime.now().year)]

        output_dir = self.data_root / "etf_daily_wide_partitioned"

        for year in years:
            logger.info(f"构建 ETF 宽表: {year}")
            df = self._join_etf_tables(year)
            if df is not None and not df.is_empty():
                year_dir = output_dir / f"year={year}"
                year_dir.mkdir(parents=True, exist_ok=True)
                df.write_parquet(year_dir / "data.parquet")
                logger.info(f"  写入 {len(df)} 行 -> {year_dir}")

    def _join_stock_tables(self, year: str) -> pl.DataFrame | None:
        """JOIN 股票相关表为宽表"""
        try:
            # 行情（含后复权字段）
            price = self._read_year("stock_daily_price", year)
            if price is None or price.is_empty():
                return None

            # 估值
            valuation = self._read_year("stock_valuation", year)
            # 融资融券
            margin = self._read_year("stock_margin_trading", year)
            # 资金流
            money_flow = self._read_year("stock_money_flow", year)
            # 行业（最新截面）
            industry = self._read_year("stock_industry", year)
            # ST状态
            st_status = self._read_year("stock_st_status", year)

            df = price

            # 逐步 LEFT JOIN
            join_keys = ["date", "code"]
            if valuation is not None and not valuation.is_empty():
                df = df.join(valuation, on=join_keys, how="left", suffix="_val")
            if margin is not None and not margin.is_empty():
                df = df.join(margin, on=join_keys, how="left", suffix="_margin")
            if money_flow is not None and not money_flow.is_empty():
                df = df.join(money_flow, on=join_keys, how="left", suffix="_flow")
            if st_status is not None and not st_status.is_empty():
                df = df.join(st_status, on=join_keys, how="left", suffix="_st")
            if industry is not None and not industry.is_empty():
                # 行业可能每日更新，取每只股票最新行业
                industry_latest = industry.sort("date").unique(
                    subset=["code"], keep="last"
                ).drop("date")
                df = df.join(industry_latest, on="code", how="left", suffix="_ind")

            return df
        except Exception as e:
            logger.error(f"构建股票宽表失败 {year}: {e}")
            return None

    def _join_etf_tables(self, year: str) -> pl.DataFrame | None:
        """JOIN ETF 相关表为宽表"""
        try:
            price = self._read_year("etf_daily_price", year)
            if price is None or price.is_empty():
                return None

            margin = self._read_year("etf_margin_trading", year)
            share = self._read_year("etf_share", year)

            df = price
            join_keys = ["date", "code"]
            if margin is not None and not margin.is_empty():
                df = df.join(margin, on=join_keys, how="left", suffix="_margin")
            if share is not None and not share.is_empty():
                df = df.join(share, on=join_keys, how="left", suffix="_share")

            return df
        except Exception as e:
            logger.error(f"构建 ETF 宽表失败 {year}: {e}")
            return None

    def _read_year(self, subdir: str, year: str) -> pl.DataFrame | None:
        """读取某年某子目录的 Parquet"""
        path = self.parquet_root / subdir / f"year={year}" / "data.parquet"
        if not path.exists():
            # 尝试不分区的结构
            pattern = str(self.parquet_root / subdir / "**" / "*.parquet")
            try:
                lf = pl.scan_parquet(pattern, hive_partitioning=True)
                return lf.filter(pl.col("year") == int(year)).collect()  # type: ignore
            except Exception:
                return None
        try:
            return pl.read_parquet(path)
        except Exception as e:
            logger.debug(f"读取 {path} 失败: {e}")
            return None

    def _list_years(self, subdir: str) -> list[str]:
        """列出子目录中所有年份"""
        base = self.parquet_root / subdir
        if not base.exists():
            return [str(datetime.now().year)]
        years = []
        for d in base.iterdir():
            if d.is_dir() and d.name.startswith("year="):
                years.append(d.name.replace("year=", ""))
        return sorted(years)


__all__ = ["WideTableBuilder"]
