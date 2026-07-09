"""股票池/ETF池管理

从 YAML 配置加载股票池定义，支持动态池（基于指数成分股）和静态池。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import yaml

from ..core.logging import get_logger
from ..core.types import Code

logger = get_logger(__name__)


def load_pools(config_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """从 YAML 加载股票池定义

    Args:
        config_path: 配置文件路径，None 则用默认 config/pools.yaml

    Returns:
        {pool_name: {"stocks": [...], "weight_range": [min, max], "description": "..."}}
    """
    if config_path is None:
        # 推断项目根目录
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "config" / "pools.yaml").exists():
                config_path = parent / "config" / "pools.yaml"
                break
        else:
            logger.warning("未找到 config/pools.yaml，返回空池")
            return {}

    config_path = Path(config_path)
    if not config_path.exists():
        logger.warning(f"股票池配置不存在: {config_path}")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        pools = yaml.safe_load(f) or {}

    logger.info(f"加载股票池: {list(pools.keys())}")
    return pools


def get_pool_stocks(
    pool_name: str,
    pools: dict[str, dict[str, Any]] | None = None,
) -> list[Code]:
    """获取池中的股票代码列表"""
    if pools is None:
        pools = load_pools()
    pool = pools.get(pool_name, {})
    return pool.get("stocks", [])


def get_pool_definitions() -> dict[str, dict[str, Any]]:
    """获取所有池定义（load_pools 的别名）"""
    return load_pools()


def resolve_dynamic_pool(
    index_code: str,
    source: Any,
    date: str | None = None,
) -> list[Code]:
    """解析动态池（基于指数成分股）

    Args:
        index_code: 指数代码（如 "000300.XSHG"）
        source: DataSource 实例（需支持查询成分股）
        date: 日期，None 则最新

    Returns:
        成分股代码列表
    """
    # 尝试从数据源加载指数成分股
    if hasattr(source, "load_index_constituents"):
        return source.load_index_constituents(index_code, date)

    logger.warning(f"数据源不支持加载指数成分股: {index_code}")
    return []


__all__ = [
    "load_pools",
    "get_pool_stocks",
    "get_pool_definitions",
    "resolve_dynamic_pool",
]
