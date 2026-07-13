"""数据抽象层

提供统一的数据访问接口，兼容 download_a_share 数据目录。
"""
from .base import DataCatalog, DataSource, build_ohlcv_matrices, pivot_to_wide
from .calendar import TradeCalendar
from .sources import DuckDBSource, LocalParquetSource
from .universe import get_pool_definitions, get_pool_stocks, load_pools

__all__ = [
    "DataSource",
    "DataCatalog",
    "pivot_to_wide",
    "build_ohlcv_matrices",
    "TradeCalendar",
    "DuckDBSource",
    "LocalParquetSource",
    "load_pools",
    "get_pool_stocks",
    "get_pool_definitions",
]
