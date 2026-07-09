"""本地 Parquet 数据源

直接用 polars 扫描 Parquet 文件，兼容 download_a_share 的数据目录。
不需要 DuckDB，适合轻量场景。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_data_source
from ...core.types import Code, DateLike
from ..base import DataSource

logger = get_logger(__name__)


@register_data_source("local_parquet")
class LocalParquetSource(DataSource):
    """本地 Parquet 数据源

    用 polars 直接扫描 Parquet 文件，惰性加载 + 谓词下推。
    兼容 download_a_share 的数据目录结构。

    用法:
        source = LocalParquetSource({"data_root": "D:/Work/Project/download_a_share/data"})
        df = source.load_daily_price(["000001.SZ"], "2024-01-01", "2024-12-31")
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.data_root = Path(cfg.get("data_root", "D:/Work/Project/download_a_share/data"))

    def _scan_wide_table(self, table: str) -> pl.LazyFrame:
        """扫描宽表 Parquet（惰性）"""
        pattern = str(self.data_root / f"{table}_wide_partitioned" / "**" / "*.parquet")
        return pl.scan_parquet(pattern, hive_partitioning=True)

    def _scan_parquet(self, subdir: str) -> pl.LazyFrame:
        """扫描 parquet/ 子目录"""
        pattern = str(self.data_root / "parquet" / subdir / "**" / "*.parquet")
        return pl.scan_parquet(pattern, hive_partitioning=True)

    def load_daily_price(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        """加载日频行情（从宽表）"""
        if not codes:
            return pl.DataFrame()

        asset_type = self._detect_asset_type(codes[0])
        table = "etf_daily" if asset_type == "etf" else "stock_daily"
        lf = self._scan_wide_table(table)

        codes_normalized = [self.normalize_code(c) for c in codes]
        lf = lf.filter(pl.col("code").is_in(codes_normalized))

        if start_date is not None:
            lf = lf.filter(pl.col("date") >= pl.lit(start_date).str.to_date())
        if end_date is not None:
            lf = lf.filter(pl.col("date") <= pl.lit(end_date).str.to_date())

        prefix = "postfq_" if adjust == "post" else ""
        select_exprs = [
            pl.col("date"),
            pl.col("code"),
            pl.col(f"{prefix}open").alias("open"),
            pl.col(f"{prefix}high").alias("high"),
            pl.col(f"{prefix}low").alias("low"),
            pl.col(f"{prefix}close").alias("close"),
            pl.col(f"{prefix}volume").alias("volume"),
            pl.col("money"),
        ]
        # 添加可选字段
        schema = lf.collect_schema()
        for extra in ["paused", "high_limit", "low_limit"]:
            if extra in schema.names():
                select_exprs.append(pl.col(extra))

        df = lf.select(select_exprs).sort(["code", "date"]).collect()
        df = df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )
        return df

    def load_valuation(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载估值数据（从宽表）"""
        if not codes:
            return pl.DataFrame()

        lf = self._scan_wide_table("stock_daily")
        codes_normalized = [self.normalize_code(c) for c in codes]
        lf = lf.filter(pl.col("code").is_in(codes_normalized))

        if start_date is not None:
            lf = lf.filter(pl.col("date") >= pl.lit(start_date).str.to_date())
        if end_date is not None:
            lf = lf.filter(pl.col("date") <= pl.lit(end_date).str.to_date())

        val_cols = [
            "turnover_ratio", "market_cap", "circulating_market_cap",
            "pe_ratio", "pe_ratio_lyr", "pb_ratio", "ps_ratio",
            "pcf_ratio", "pcf_ratio2", "capitalization", "circulating_cap",
            "dividend_ratio",
        ]
        schema = lf.collect_schema()
        available = [c for c in val_cols if c in schema.names()]

        df = lf.select(["date", "code"] + available).sort(["code", "date"]).collect()
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_money_flow(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载资金流向（从宽表）"""
        if not codes:
            return pl.DataFrame()

        lf = self._scan_wide_table("stock_daily")
        codes_normalized = [self.normalize_code(c) for c in codes]
        lf = lf.filter(pl.col("code").is_in(codes_normalized))

        if start_date is not None:
            lf = lf.filter(pl.col("date") >= pl.lit(start_date).str.to_date())
        if end_date is not None:
            lf = lf.filter(pl.col("date") <= pl.lit(end_date).str.to_date())

        flow_cols = [
            "fin_value", "fin_buy_value", "fin_refund_value",
            "sec_value", "sec_sell_value", "sec_refund_value", "fin_sec_value",
            "inflow_l", "inflow_m", "inflow_s", "inflow_xl",
            "outflow_l", "outflow_m", "outflow_s", "outflow_xl",
        ]
        schema = lf.collect_schema()
        available = [c for c in flow_cols if c in schema.names()]

        df = lf.select(["date", "code"] + available).sort(["code", "date"]).collect()
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_margin(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载融资融券（从宽表）"""
        return self.load_money_flow(codes, start_date, end_date)

    def load_industry_map(self, date: DateLike | None = None) -> dict[str, str]:
        """加载行业映射"""
        lf = self._scan_wide_table("stock_daily")
        if date is not None:
            lf = lf.filter(pl.col("date") <= pl.lit(date).str.to_date())

        schema = lf.collect_schema()
        if "sw_l1_name" not in schema.names():
            return {}

        df = (
            lf.select(["code", "sw_l1_name"])
            .drop_nulls("sw_l1_name")
            .unique(subset=["code"], keep="last")
            .collect()
        )

        return {
            self.denormalize_code(row["code"]): row["sw_l1_name"]
            for row in df.iter_rows(named=True)
        }

    def load_index_data(
        self,
        index_code: Code,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载指数行情"""
        lf = self._scan_parquet("index_daily_price")
        code_normalized = self.normalize_code(index_code)
        lf = lf.filter(pl.col("code") == code_normalized)

        if start_date is not None:
            lf = lf.filter(pl.col("date") >= pl.lit(start_date).str.to_date())
        if end_date is not None:
            lf = lf.filter(pl.col("date") <= pl.lit(end_date).str.to_date())

        df = lf.sort("date").collect()
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def get_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        """获取交易日历"""
        try:
            lf = self._scan_parquet("trade_calendar")
            df = (
                lf.filter(
                    (pl.col("is_trade_day") == True)
                    & (pl.col("date") >= pl.lit(start_date).str.to_date())
                    & (pl.col("date") <= pl.lit(end_date).str.to_date())
                )
                .sort("date")
                .collect()
            )
            return df["date"].dt.strftime("%Y-%m-%d").to_list()
        except Exception as e:
            logger.warning(f"获取交易日历失败: {e}")
            from .calendar import TradeCalendar

            return TradeCalendar._builtin_calendar(start_date, end_date)

    def get_latest_date(self) -> str:
        """获取最新数据日期"""
        try:
            lf = self._scan_wide_table("stock_daily")
            df = lf.select(pl.col("date").max()).collect()
            latest = df["date"][0]
            if hasattr(latest, "strftime"):
                return latest.strftime("%Y-%m-%d")
            return str(latest)[:10]
        except Exception:
            from datetime import date

            return date.today().strftime("%Y-%m-%d")

    def filter_tradable(self, codes: list[Code], date: DateLike | None = None) -> set[Code]:
        """过滤可交易标的"""
        if not codes:
            return set()
        lf = self._scan_wide_table("stock_daily")
        codes_normalized = [self.normalize_code(c) for c in codes]
        lf = lf.filter(pl.col("code").is_in(codes_normalized))

        schema = lf.collect_schema()
        filter_exprs = []
        if "paused" in schema.names():
            filter_exprs.append(pl.col("paused") == False)
        if "is_st" in schema.names():
            filter_exprs.append(pl.col("is_st") == False)

        if date is not None:
            lf = lf.filter(pl.col("date") == pl.lit(date).str.to_date())
        else:
            latest = self.get_latest_date()
            lf = lf.filter(pl.col("date") == pl.lit(latest).str.to_date())

        if filter_exprs:
            combined = filter_exprs[0]
            for expr in filter_exprs[1:]:
                combined = combined & expr
            lf = lf.filter(combined)

        try:
            df = lf.select("code").collect()
            return {self.denormalize_code(c) for c in df["code"].to_list()}
        except Exception:
            return set(codes)

    def get_all_stocks(self, date: DateLike | None = None) -> list[Code]:
        """获取全部股票代码"""
        lf = self._scan_wide_table("stock_daily")
        if date is not None:
            lf = lf.filter(pl.col("date") == pl.lit(date).str.to_date())
        else:
            latest = self.get_latest_date()
            lf = lf.filter(pl.col("date") == pl.lit(latest).str.to_date())
        try:
            df = lf.select("code").unique().collect()
            return [self.denormalize_code(c) for c in df["code"].to_list()]
        except Exception:
            return []

    def get_all_etfs(self, date: DateLike | None = None) -> list[Code]:
        """获取全部ETF代码"""
        lf = self._scan_wide_table("etf_daily")
        if date is not None:
            lf = lf.filter(pl.col("date") == pl.lit(date).str.to_date())
        else:
            latest = self.get_latest_date()
            lf = lf.filter(pl.col("date") == pl.lit(latest).str.to_date())
        try:
            df = lf.select("code").unique().collect()
            return [self.denormalize_code(c) for c in df["code"].to_list()]
        except Exception:
            return []

    @staticmethod
    def _detect_asset_type(code: str) -> str:
        """检测资产类型"""
        if "." not in code:
            return "stock"
        prefix = code.split(".")[0]
        if prefix[:2] in ("51", "15", "16", "52", "56", "59"):
            return "etf"
        return "stock"


__all__ = ["LocalParquetSource"]
