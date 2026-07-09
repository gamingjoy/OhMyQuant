"""CSV 数据源（测试用）

从 CSV 文件加载数据，用于单元测试和快速原型验证。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_data_source
from ...core.types import Code, DateLike
from ..base import DataSource

logger = get_logger(__name__)


@register_data_source("csv")
class CSVSource(DataSource):
    """CSV 数据源

    目录结构:
        data_dir/
        ├── daily_price.csv      (date, code, open, high, low, close, volume, money)
        ├── valuation.csv        (date, code, pe_ratio, pb_ratio, ...)
        ├── index_data.csv       (date, code, open, high, low, close, volume)
        └── trade_calendar.csv   (date, is_trade_day)
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.data_dir = Path(cfg.get("data_dir", "data"))

    def _read_csv(self, filename: str) -> pl.DataFrame:
        path = self.data_dir / filename
        if not path.exists():
            logger.warning(f"CSV 文件不存在: {path}")
            return pl.DataFrame()
        df = pl.read_csv(path, try_parse_dates=True)
        return df

    @staticmethod
    def _filter_by_date(
        df: pl.DataFrame,
        start_date: DateLike | None,
        end_date: DateLike | None,
    ) -> pl.DataFrame:
        """按日期过滤，自动处理字符串与 date 类型的比较"""
        if df.is_empty() or "date" not in df.columns:
            return df
        # 确保日期列为字符串格式以便与字符串比较
        if df.schema["date"] != pl.Utf8:
            df = df.with_columns(pl.col("date").cast(pl.Utf8))
        if start_date is not None:
            start_str = str(start_date)
            df = df.filter(pl.col("date") >= start_str)
        if end_date is not None:
            end_str = str(end_date)
            df = df.filter(pl.col("date") <= end_str)
        return df

    def load_daily_price(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        df = self._read_csv("daily_price.csv")
        if df.is_empty():
            return df
        df = df.filter(pl.col("code").is_in(codes))
        df = self._filter_by_date(df, start_date, end_date)
        return df.sort(["code", "date"])

    def load_valuation(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
        df = self._read_csv("valuation.csv")
        if df.is_empty():
            return df
        df = df.filter(pl.col("code").is_in(codes))
        df = self._filter_by_date(df, start_date, end_date)
        return df.sort(["code", "date"])

    def load_money_flow(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
        return pl.DataFrame()

    def load_margin(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
        return pl.DataFrame()

    def load_industry_map(self, date=None) -> dict[str, str]:
        df = self._read_csv("industry.csv")
        if df.is_empty():
            return {}
        return {row["code"]: row["industry"] for row in df.iter_rows(named=True)}

    def load_index_data(self, index_code, start_date=None, end_date=None) -> pl.DataFrame:
        df = self._read_csv("index_data.csv")
        if df.is_empty():
            return df
        df = df.filter(pl.col("code") == index_code)
        if start_date is not None:
            df = df.filter(pl.col("date") >= pl.lit(start_date))
        if end_date is not None:
            df = df.filter(pl.col("date") <= pl.lit(end_date))
        return df.sort("date")

    def get_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        df = self._read_csv("trade_calendar.csv")
        if df.is_empty():
            from .calendar import TradeCalendar

            return TradeCalendar._builtin_calendar(start_date, end_date)
        df = df.filter(pl.col("is_trade_day") == True)
        df = df.filter(
            (pl.col("date") >= pl.lit(start_date))
            & (pl.col("date") <= pl.lit(end_date))
        )
        return df["date"].dt.strftime("%Y-%m-%d").to_list()

    def get_latest_date(self) -> str:
        df = self._read_csv("daily_price.csv")
        if df.is_empty():
            from datetime import date

            return date.today().strftime("%Y-%m-%d")
        return str(df["date"].max())[:10]


__all__ = ["CSVSource"]
