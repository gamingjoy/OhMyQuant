"""聚宽数据源

封装 jqdatasdk API，支持在线下载 22+ 数据类型。
凭证从环境变量或配置中读取。

数据类型（参考 download_a_share/config.py）:
  股票: 行情/估值/ST状态/融资融券/资金流/行业/概念/财报/龙虎榜/限售/沪深港通
  指数: 日频行情
  ETF: 行情/净值/份额/融资融券/持仓
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_data_source
from ...core.types import Code, DateLike
from ..base import DataSource

logger = get_logger(__name__)

# 聚宽下载字段（后复权）
PRICE_FIELDS = [
    "open", "close", "high", "low",
    "volume", "money", "factor",
    "high_limit", "low_limit", "avg", "pre_close", "paused",
]

VALUATION_FIELDS = [
    "turnover_ratio", "market_cap", "circulating_market_cap",
    "pe_ratio", "pe_ratio_lyr", "pb_ratio", "ps_ratio",
    "pcf_ratio", "pcf_ratio2", "capitalization", "circulating_cap",
    "dividend_ratio",
]

INDEX_CODES = {
    "000300.XSHG": "沪深300",
    "000905.XSHG": "中证500",
    "000852.XSHG": "中证1000",
    "000016.XSHG": "上证50",
    "000688.XSHG": "科创50",
    "399006.XSHE": "创业板指",
}


@register_data_source("jqdata")
class JQDataSource(DataSource):
    """聚宽数据源（在线下载）

    凭证从环境变量 JQ_USERNAME / JQ_PASSWORD 读取，
    或通过 config 传入。

    用法:
        source = JQDataSource({"username": "...", "password": "..."})
        df = source.load_daily_price(["000001.XSHE"], "2024-01-01", "2024-12-31")
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.username = cfg.get("username") or os.getenv("JQ_USERNAME")
        self.password = cfg.get("password") or os.getenv("JQ_PASSWORD")
        self._authenticated = False
        self._jq: Any = None

    def _ensure_auth(self):
        """确保已认证"""
        if self._authenticated:
            return
        if not self.username or not self.password:
            raise ValueError(
                "聚宽凭证未配置，请设置 JQ_USERNAME/JQ_PASSWORD 环境变量或通过 config 传入"
            )
        try:
            import jqdatasdk as jq
        except ImportError as e:
            raise ImportError("jqdatasdk 未安装，请运行: pip install jqdatasdk") from e

        self._jq = jq
        jq.auth(self.username, self.password)
        self._authenticated = True
        logger.info(f"聚宽认证成功，剩余查询额度: {jq.get_query_count()}")

    def load_daily_price(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        """加载日频行情（在线下载）"""
        self._ensure_auth()
        codes_normalized = [self.normalize_code(c) for c in codes]

        fq = adjust if adjust != "none" else None
        pdf = self._jq.get_price(
            codes_normalized,
            start_date=start_date,
            end_date=end_date,
            frequency="daily",
            fields=["open", "close", "high", "low", "volume", "money",
                    "high_limit", "low_limit", "avg", "pre_close", "paused"],
            fq=fq,
            panel=False,
        )
        df = pl.from_pandas(pdf)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_valuation(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
        """加载估值数据"""
        self._ensure_auth()
        codes_normalized = [self.normalize_code(c) for c in codes]
        pdf = self._jq.get_valuation(
            codes_normalized,
            start_date=start_date,
            end_date=end_date,
            fields=VALUATION_FIELDS,
            panel=False,
        )
        df = pl.from_pandas(pdf)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_money_flow(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
        """加载资金流向"""
        self._ensure_auth()
        codes_normalized = [self.normalize_code(c) for c in codes]
        pdf = self._jq.get_money_flow(
            codes_normalized,
            start_date=start_date,
            end_date=end_date,
            fields=["sec_purchase_amount", "sec_repurchase_amount",
                    "change_percent", "net_amount", "net_amount_xl",
                    "net_amount_l", "net_amount_m", "net_amount_s"],
            count=None,
        )
        df = pl.from_pandas(pdf).rename({"time": "date"})
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_margin(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
        """加载融资融券"""
        self._ensure_auth()
        codes_normalized = [self.normalize_code(c) for c in codes]
        pdf = self._jq.get_marginsec(
            codes_normalized,
            start_date=start_date,
            end_date=end_date,
            fields=["fin_value", "fin_buy_value", "fin_refund_value",
                    "sec_value", "sec_sell_value", "sec_refund_value",
                    "fin_sec_value"],
        )
        df = pl.from_pandas(pdf).rename({"time": "date"})
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_industry_map(self, date=None) -> dict[str, str]:
        """加载行业映射（申万一级行业）"""
        self._ensure_auth()
        try:
            df = self._jq.get_industry(securities="*", date=date)
            result: dict[str, str] = {}
            for code, industries in df.items():
                if "sw_l1" in industries:
                    result[self.denormalize_code(code)] = industries["sw_l1"].get(
                        "industry_code", ""
                    )
            return result
        except Exception as e:
            logger.warning(f"加载行业映射失败: {e}")
            return {}

    def load_index_data(self, index_code, start_date=None, end_date=None) -> pl.DataFrame:
        """加载指数行情"""
        self._ensure_auth()
        code_normalized = self.normalize_code(index_code)
        pdf = self._jq.get_price(
            code_normalized,
            start_date=start_date,
            end_date=end_date,
            frequency="daily",
            fields=["open", "close", "high", "low", "volume", "money", "pre_close", "avg"],
            fq=None,
            panel=False,
        )
        df = pl.from_pandas(pdf)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def get_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        """获取交易日历"""
        self._ensure_auth()
        days = self._jq.get_trade_days(start_date=start_date, end_date=end_date)
        return [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in days]

    def get_latest_date(self) -> str:
        """获取最新数据日期（昨天）"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return yesterday

    def get_all_stocks(self, date=None) -> list[Code]:
        """获取全部股票代码"""
        self._ensure_auth()
        target_date = date or self.get_latest_date()
        stocks = self._jq.get_all_securities(types=["stock"], date=target_date)
        return [self.denormalize_code(c) for c in stocks.index.tolist()]

    def get_all_etfs(self, date=None) -> list[Code]:
        """获取全部ETF代码"""
        self._ensure_auth()
        target_date = date or self.get_latest_date()
        etfs = self._jq.get_all_securities(types=["etf"], date=target_date)
        return [self.denormalize_code(c) for c in etfs.index.tolist()]


__all__ = ["JQDataSource"]
