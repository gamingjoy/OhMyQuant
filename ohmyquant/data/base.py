"""数据抽象层核心接口

定义 DataSource ABC 和 DataCatalog 统一访问入口。
所有数据源（聚宽/本地Parquet/DuckDB/CSV）实现 DataSource 接口，
上层引擎只依赖此接口，不关心数据来源。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import polars as pl

from ..core.cache import LRUCache
from ..core.logging import get_logger
from ..core.types import Code, DateLike

logger = get_logger(__name__)


class DataSource(ABC):
    """数据源抽象基类

    所有数据源实现此接口。上层引擎通过 DataCatalog 访问数据，
    不直接依赖具体数据源实现。
    """

    @abstractmethod
    def load_daily_price(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        """加载日频行情数据

        Args:
            codes: 证券代码列表
            start_date: 开始日期（含），None 则不限
            end_date: 结束日期（含），None 则不限
            adjust: 复权方式 "post"(后复权) / "none"(未复权) / "pre"(前复权)

        Returns:
            长表格式，列: date, code, open, high, low, close, volume, money
        """
        ...

    @abstractmethod
    def load_valuation(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载估值数据（PE/PB/换手率/市值等）"""
        ...

    @abstractmethod
    def load_money_flow(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载资金流向数据"""
        ...

    @abstractmethod
    def load_margin(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载融资融券数据"""
        ...

    @abstractmethod
    def load_industry_map(self, date: DateLike | None = None) -> dict[str, str]:
        """加载行业映射 {code: industry_name}"""
        ...

    @abstractmethod
    def load_index_data(
        self,
        index_code: Code,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载指数行情"""
        ...

    @abstractmethod
    def get_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        """获取交易日历"""
        ...

    @abstractmethod
    def get_latest_date(self) -> str:
        """获取最新数据日期（YYYY-MM-DD）"""
        ...

    def filter_tradable(self, codes: list[Code], date: DateLike | None = None) -> set[Code]:
        """过滤可交易标的（非ST/非停牌）

        默认实现：全部可交易。子类可覆盖。
        """
        return set(codes)

    def get_all_stocks(self, date: DateLike | None = None) -> list[Code]:
        """获取全部股票代码"""
        return []

    def get_all_etfs(self, date: DateLike | None = None) -> list[Code]:
        """获取全部ETF代码"""
        return []

    # ------------------------------------------------------------------
    # 扩展数据（默认实现返回空，子类按需覆盖）
    # ------------------------------------------------------------------

    def load_financial_statement(
        self,
        statement_type: str,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载财务报表

        Args:
            statement_type: income / balance / cash_flow / indicator
            codes: 股票代码列表
        """
        return pl.DataFrame()

    def load_billboard(
        self,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载龙虎榜数据"""
        return pl.DataFrame()

    def load_hk_holdings(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载沪深港通持股（北向资金）"""
        return pl.DataFrame()

    def load_locked_shares(
        self,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载限售解禁数据"""
        return pl.DataFrame()

    def load_factor_wide(
        self,
        factor_names: list[str] | None = None,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载因子宽表（预计算因子）"""
        return pl.DataFrame()

    def load_index_constituents(
        self,
        index_code: Code,
        date: DateLike | None = None,
    ) -> list[Code]:
        """加载指数成分股（支持时点查询）"""
        return []

    # ------------------------------------------------------------------
    # 代码标准化工具（子类可覆盖）
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_code(code: str) -> str:
        """标准化代码为聚宽格式

        "000001.SZ" → "000001.XSHE"
        "600000.SH" → "600000.XSHG"
        已是聚宽格式则不变
        """
        if "." not in code:
            return code
        prefix, suffix = code.rsplit(".", 1)
        suffix = suffix.upper()
        if suffix in ("SH", "XSHG"):
            return f"{prefix}.XSHG"
        elif suffix in ("SZ", "XSHE"):
            return f"{prefix}.XSHE"
        return code

    @staticmethod
    def denormalize_code(code: str) -> str:
        """聚宽代码转回常规格式

        "000001.XSHE" → "000001.SZ"
        "600000.XSHG" → "600000.SH"
        """
        if "." not in code:
            return code
        prefix, suffix = code.rsplit(".", 1)
        suffix = suffix.upper()
        if suffix == "XSHG":
            return f"{prefix}.SH"
        elif suffix == "XSHE":
            return f"{prefix}.SZ"
        return code


def pivot_to_wide(df: pl.DataFrame, value_col: str) -> pl.DataFrame:
    """长表转宽表（date × code 矩阵）

    Args:
        df: 长表，至少含 date, code, value_col 三列
        value_col: 值列名

    Returns:
        宽表，索引为 date，列为 code
    """
    return df.pivot(values=value_col, index="date", on="code").sort("date")


def build_ohlcv_matrices(df: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """将长表行情转为宽表矩阵

    Args:
        df: 长表行情，含 date, code, open, high, low, close, volume, money

    Returns:
        {"open": wide_df, "high": ..., "low": ..., "close": ..., "volume": ..., "money": ...}
    """
    result = {}
    for col in ["open", "high", "low", "close", "volume", "money"]:
        if col in df.columns:
            result[col] = pivot_to_wide(df, col)
    return result


class DataCatalog:
    """数据目录 - 统一数据访问入口（带缓存）

    所有模块通过 DataCatalog 访问数据，不直接操作 DataSource。
    提供内存缓存避免重复加载。

    用法:
        catalog = DataCatalog(DuckDBSource())
        price = catalog.get_daily_price(["000001.SZ"], "2020-01-01", "2024-12-31")
        ohlcv = catalog.get_ohlcv(["000001.SZ"], "2020-01-01", "2024-12-31")
    """

    def __init__(
        self,
        source: DataSource,
        cache_size: int = 32,
        cache_dir: str | Path | None = None,
    ):
        self.source = source
        self._cache = LRUCache(maxsize=cache_size)
        self._disk_cache_dir = Path(cache_dir) if cache_dir else None

    def _cache_key(self, method: str, *args, **kwargs) -> str:
        """生成缓存 key"""
        codes = args[0] if args else kwargs.get("codes", [])
        if isinstance(codes, list):
            codes = tuple(sorted(codes))
        return f"{method}:{codes}:{args[1:]}:{sorted(kwargs.items())}"

    # ------------------------------------------------------------------
    # 行情数据
    # ------------------------------------------------------------------

    def get_daily_price(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        """获取日频行情（带内存缓存）"""
        key = self._cache_key("daily_price", codes, start_date, end_date, adjust=adjust)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        data = self.source.load_daily_price(codes, start_date, end_date, adjust)
        self._cache.set(key, data)
        return data

    def get_ohlcv(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> dict[str, pl.DataFrame]:
        """获取 OHLCV 宽表矩阵

        Returns:
            {"open": wide_df, "high": ..., "low": ..., "close": ..., "volume": ..., "money": ...}
        """
        df = self.get_daily_price(codes, start_date, end_date, adjust)
        return build_ohlcv_matrices(df)

    def get_close(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        """获取收盘价宽表"""
        df = self.get_daily_price(codes, start_date, end_date, adjust)
        return pivot_to_wide(df, "close")

    # ------------------------------------------------------------------
    # 基本面数据
    # ------------------------------------------------------------------

    def get_valuation(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取估值数据"""
        return self.source.load_valuation(codes, start_date, end_date)

    def get_money_flow(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取资金流向"""
        return self.source.load_money_flow(codes, start_date, end_date)

    def get_margin(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取融资融券"""
        return self.source.load_margin(codes, start_date, end_date)

    def get_industry_map(self, date: DateLike | None = None) -> dict[str, str]:
        """获取行业映射"""
        return self.source.load_industry_map(date)

    def get_index_data(
        self,
        index_code: Code,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取指数行情"""
        return self.source.load_index_data(index_code, start_date, end_date)

    # ------------------------------------------------------------------
    # 交易日历与元数据
    # ------------------------------------------------------------------

    def get_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        """获取交易日历"""
        return self.source.get_trade_calendar(start_date, end_date)

    def get_latest_date(self) -> str:
        """获取最新数据日期"""
        return self.source.get_latest_date()

    def filter_tradable(self, codes: list[Code], date: DateLike | None = None) -> set[Code]:
        """过滤可交易标的"""
        return self.source.filter_tradable(codes, date)

    def get_all_stocks(self, date: DateLike | None = None) -> list[Code]:
        """获取全部股票"""
        return self.source.get_all_stocks(date)

    def get_all_etfs(self, date: DateLike | None = None) -> list[Code]:
        """获取全部ETF"""
        return self.source.get_all_etfs(date)

    # ------------------------------------------------------------------
    # 扩展数据代理方法
    # ------------------------------------------------------------------

    def get_financial_statement(
        self,
        statement_type: str,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取财务报表"""
        return self.source.load_financial_statement(
            statement_type, codes, start_date, end_date
        )

    def get_billboard(
        self,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取龙虎榜数据"""
        return self.source.load_billboard(codes, start_date, end_date)

    def get_hk_holdings(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取北向资金持股"""
        return self.source.load_hk_holdings(codes, start_date, end_date)

    def get_locked_shares(
        self,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取限售解禁数据"""
        return self.source.load_locked_shares(codes, start_date, end_date)

    def get_factor_wide(
        self,
        factor_names: list[str] | None = None,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """获取因子宽表"""
        return self.source.load_factor_wide(
            factor_names, codes, start_date, end_date
        )

    def get_index_constituents(
        self,
        index_code: Code,
        date: DateLike | None = None,
    ) -> list[Code]:
        """获取指数成分股"""
        return self.source.load_index_constituents(index_code, date)

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """清空内存缓存"""
        self._cache.clear()

    @property
    def source_name(self) -> str:
        return type(self.source).__name__


__all__ = [
    "DataSource",
    "DataCatalog",
    "pivot_to_wide",
    "build_ohlcv_matrices",
]
