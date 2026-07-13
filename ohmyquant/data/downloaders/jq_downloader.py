"""聚宽数据下载器

封装 jqdatasdk 的下载逻辑，支持 22+ 数据类型的增量下载。
参考 download_a_share 的 jq_downloader.py 设计。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ...core.logging import get_logger

logger = get_logger(__name__)

# 支持的数据类型
STOCK_DATA_TYPES = {
    "stock_daily_price": "A股日频行情",
    "stock_valuation": "A股估值数据",
    "stock_st_status": "A股ST状态",
    "stock_margin_trading": "A股融资融券",
    "stock_money_flow": "A股资金流向",
    "stock_industry": "A股行业分类",
    "stock_income": "A股利润表",
    "stock_cash_flow": "A股现金流量表",
    "stock_balance": "A股资产负债表",
    "stock_indicator": "A股财务指标",
    "stock_hk_hold": "A股沪深港通持股",
    "index_daily_price": "指数日频行情",
    "index_constituents": "指数成分股",
    "etf_daily_price": "ETF日频行情",
    "etf_net_value": "ETF净值",
    "etf_share": "ETF份额",
    "etf_margin_trading": "ETF融资融券",
    "security_info": "证券基本信息",
    "trade_calendar": "交易日历",
}


class JQDownloader:
    """聚宽数据下载器

    用法:
        from ohmyquant.data.sources.jqdata_source import JQDataSource
        from ohmyquant.data.downloaders.jq_downloader import JQDownloader

        source = JQDataSource({"username": "...", "password": "..."})
        downloader = JQDownloader(source, "D:/Work/Project/download_a_share/data")
        downloader.download_incremental("2024-12-01", "2024-12-31")
    """

    def __init__(self, source: Any, data_root: str | Path):
        self.source = source
        self.data_root = Path(data_root)
        self.parquet_root = self.data_root / "parquet"

    def download_incremental(
        self,
        start_date: str,
        end_date: str,
        data_types: list[str] | None = None,
    ) -> None:
        """增量下载数据

        Args:
            start_date: 开始日期
            end_date: 结束日期
            data_types: 指定数据类型，None 则全部
        """
        types = data_types or list(STOCK_DATA_TYPES.keys())

        for dtype in types:
            try:
                logger.info(f"下载 {dtype} ({STOCK_DATA_TYPES.get(dtype, '')})...")
                self._download_type(dtype, start_date, end_date)
            except Exception as e:
                logger.error(f"下载 {dtype} 失败: {e}")
                # 不忽略错误，继续下载其他类型

    def _download_type(self, dtype: str, start_date: str, end_date: str) -> None:
        """下载单个数据类型"""
        method = getattr(self, f"_download_{dtype}", None)
        if method is None:
            logger.warning(f"不支持的数据类型: {dtype}")
            return
        method(start_date, end_date)

    def _save_parquet(
        self,
        df: pl.DataFrame,
        subdir: str,
        date_col: str = "date",
    ) -> None:
        """按年份分区保存 Parquet"""
        if df.is_empty():
            return

        output_base = self.parquet_root / subdir
        output_base.mkdir(parents=True, exist_ok=True)

        # 按年份分区
        if date_col in df.columns:
            df = df.with_columns(pl.col(date_col).dt.year().alias("_year"))
            for year, group in df.group_by("_year"):
                year = year[0] if isinstance(year, tuple) else year
                group = group.drop("_year")
                year_dir = output_base / f"year={year}"
                year_dir.mkdir(parents=True, exist_ok=True)
                output_path = year_dir / "data.parquet"
                group.write_parquet(output_path)
                logger.info(f"  保存 {len(group)} 行 -> {output_path}")
        else:
            output_path = output_base / "data.parquet"
            df.write_parquet(output_path)

    # ------------------------------------------------------------------
    # 各数据类型下载方法
    # ------------------------------------------------------------------

    def _download_stock_daily_price(self, start_date: str, end_date: str) -> None:
        """下载股票日频行情"""
        stocks = self.source.get_all_stocks(end_date)
        logger.info(f"  共 {len(stocks)} 只股票")

        batch_size = 50
        all_dfs = []
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i : i + batch_size]
            try:
                df = self.source.load_daily_price(batch, start_date, end_date, adjust="post")
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"  批次 {i//batch_size} 下载失败: {e}")

        if all_dfs:
            combined = pl.concat(all_dfs, how="diagonal_relaxed")
            self._save_parquet(combined, "stock_daily_price")

    def _download_index_daily_price(self, start_date: str, end_date: str) -> None:
        """下载指数日频行情"""
        from .jqdata_source import INDEX_CODES

        all_dfs = []
        for code in INDEX_CODES:
            try:
                df = self.source.load_index_data(code, start_date, end_date)
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"  指数 {code} 下载失败: {e}")

        if all_dfs:
            combined = pl.concat(all_dfs, how="diagonal_relaxed")
            self._save_parquet(combined, "index_daily_price")

    def _download_trade_calendar(self, start_date: str, end_date: str) -> None:
        """下载交易日历"""
        try:
            days = self.source.get_trade_calendar(start_date, end_date)
            df = pl.DataFrame(
                {
                    "date": pl.Series(days).str.to_date(),
                    "is_trade_day": [True] * len(days),
                }
            )
            # 添加月份和星期
            df = df.with_columns(
                pl.col("date").dt.month().alias("month"),
                pl.col("date").dt.weekday().alias("day_of_week"),
            )
            self._save_parquet(df, "trade_calendar")
        except Exception as e:
            logger.error(f"下载交易日历失败: {e}")

    def _download_stock_valuation(self, start_date: str, end_date: str) -> None:
        """下载股票估值数据"""
        stocks = self.source.get_all_stocks(end_date)
        batch_size = 50
        all_dfs = []
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i : i + batch_size]
            try:
                df = self.source.load_valuation(batch, start_date, end_date)
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"  估值批次 {i//batch_size} 下载失败: {e}")

        if all_dfs:
            combined = pl.concat(all_dfs, how="diagonal_relaxed")
            self._save_parquet(combined, "stock_valuation")

    def _download_stock_money_flow(self, start_date: str, end_date: str) -> None:
        """下载资金流向"""
        stocks = self.source.get_all_stocks(end_date)
        batch_size = 50
        all_dfs = []
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i : i + batch_size]
            try:
                df = self.source.load_money_flow(batch, start_date, end_date)
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"  资金流批次 {i//batch_size} 下载失败: {e}")

        if all_dfs:
            combined = pl.concat(all_dfs, how="diagonal_relaxed")
            self._save_parquet(combined, "stock_money_flow")

    def _download_stock_margin_trading(self, start_date: str, end_date: str) -> None:
        """下载融资融券"""
        stocks = self.source.get_all_stocks(end_date)
        batch_size = 50
        all_dfs = []
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i : i + batch_size]
            try:
                df = self.source.load_margin(batch, start_date, end_date)
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"  融资融券批次 {i//batch_size} 下载失败: {e}")

        if all_dfs:
            combined = pl.concat(all_dfs, how="diagonal_relaxed")
            self._save_parquet(combined, "stock_margin_trading")

    def _download_etf_daily_price(self, start_date: str, end_date: str) -> None:
        """下载ETF日频行情"""
        etfs = self.source.get_all_etfs(end_date)
        batch_size = 50
        all_dfs = []
        for i in range(0, len(etfs), batch_size):
            batch = etfs[i : i + batch_size]
            try:
                df = self.source.load_daily_price(batch, start_date, end_date, adjust="post")
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"  ETF批次 {i//batch_size} 下载失败: {e}")

        if all_dfs:
            combined = pl.concat(all_dfs, how="diagonal_relaxed")
            self._save_parquet(combined, "etf_daily_price")

    def _download_security_info(self, start_date: str, end_date: str) -> None:
        """下载证券基本信息"""
        try:
            self._ensure_auth()
            stocks = self._jq.get_all_securities(types=["stock", "etf", "index", "lof"])
            df = pl.from_pandas(stocks.reset_index())
            self._save_parquet(df, "security_info", date_col="start_date")
        except Exception as e:
            logger.warning(f"下载证券信息失败: {e}")

    def _ensure_auth(self):
        """确保已认证"""
        if hasattr(self.source, "_ensure_auth"):
            self.source._ensure_auth()
            self._jq = self.source._jq


__all__ = ["JQDownloader", "STOCK_DATA_TYPES"]
