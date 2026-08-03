"""因子库管理

提供因子注册、查找、批量计算、缓存、依赖解析等便捷功能。

特性:
  - LRU 缓存: 避免重复计算相同因子
  - 依赖解析: 自动先计算 depends_on 声明的依赖因子
  - 外部因子: 支持从外部目录加载自定义因子
"""
from __future__ import annotations

from typing import Any

import polars as pl

from ..core.cache import LRUCache
from ..core.logging import get_logger
from .base import Factor, FactorRegistry

logger = get_logger(__name__)


class FactorLibrary:
    """因子库

    管理所有已注册因子，提供批量计算和查询功能。

    用法:
        # 基本用法
        lib = FactorLibrary()
        print(lib.list_factors())
        results = lib.compute_factors(["mom_1m", "vol_20d"], ohlcv_data)

        # 带缓存
        lib = FactorLibrary(config={"use_cache": True, "cache_size": 64})

        # 加载外部因子
        lib = FactorLibrary(config={"external_paths": ["path/to/my_factors"]})
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """初始化因子库

        Args:
            config: 配置字典，支持以下键:
                - use_cache: bool, 是否启用缓存（默认 True）
                - cache_size: int, 缓存大小（默认 64）
                - external_paths: list[str], 外部因子目录路径列表
        """
        # 确保内置因子已注册
        from . import builtin  # noqa: F401

        self.config = config or {}
        self._use_cache = self.config.get("use_cache", True)
        self._cache: LRUCache | None = None
        if self._use_cache:
            self._cache = LRUCache(maxsize=self.config.get("cache_size", 64))

        # 加载外部因子
        external_paths = self.config.get("external_paths", [])
        if external_paths:
            count = FactorRegistry.discover_external(external_paths)
            if count > 0:
                logger.info(f"加载了 {count} 个外部因子模块")

    def list_factors(self, category: str | None = None) -> list[str]:
        """列出所有因子"""
        return FactorRegistry.list_factors(category)

    def list_categories(self) -> list[str]:
        """列出所有因子类别"""
        return FactorRegistry.list_categories()

    def get_factor_info(self, name: str) -> dict:
        """获取因子信息"""
        return FactorRegistry.get_info(name)

    def compute_factor(
        self,
        name: str,
        data: dict[str, pl.DataFrame],
        config: dict | None = None,
    ) -> pl.DataFrame:
        """计算单个因子

        自动处理依赖（depends_on）和缓存。

        Args:
            name: 因子名
            data: 数据字典
            config: 因子配置（覆盖 params 默认值）

        Returns:
            因子值矩阵 (date × code)
        """
        # 检查缓存
        cache_key = self._make_cache_key(name, config, data)
        if self._cache is not None and cache_key is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"缓存命中: {name}")
                return cached

        factor = FactorRegistry.create(name, config)

        # 处理因子依赖：自动计算依赖因子并加入 data
        if factor.depends_on:
            data = dict(data)  # 浅拷贝，避免修改原字典
            for dep_name in factor.depends_on:
                if dep_name not in data:
                    logger.debug(f"计算依赖因子: {dep_name} for {name}")
                    data[dep_name] = self.compute_factor(dep_name, data)

        result = factor.compute(data)

        # 写入缓存
        if self._cache is not None and cache_key is not None:
            self._cache.set(cache_key, result)

        return result

    def compute_factors(
        self,
        factor_names: list[str],
        data: dict[str, pl.DataFrame],
        config: dict[str, dict] | None = None,
    ) -> dict[str, pl.DataFrame]:
        """批量计算多个因子

        Args:
            factor_names: 因子名列表
            data: 数据字典
            config: {factor_name: config_dict}，每个因子的独立配置

        Returns:
            {factor_name: factor_values}
        """
        config = config or {}
        results = {}
        for name in factor_names:
            try:
                results[name] = self.compute_factor(name, data, config.get(name))
                logger.debug(f"计算因子: {name}")
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
        return results

    def get_factors_by_fields(self, available_fields: list[str]) -> list[str]:
        """根据可用数据字段筛选可计算的因子

        Args:
            available_fields: 可用数据字段（如 ["close", "volume", "money"]）

        Returns:
            可计算的因子名列表
        """
        all_factors = self.list_factors()
        computable = []
        for name in all_factors:
            try:
                factor = FactorRegistry.create(name)
                if all(f in available_fields for f in factor.required_fields):
                    computable.append(name)
            except Exception:
                continue
        return computable

    def clear_cache(self) -> None:
        """清空因子缓存"""
        if self._cache is not None:
            self._cache.clear()
            logger.debug("因子缓存已清空")

    def _make_cache_key(
        self,
        name: str,
        config: dict | None,
        data: dict[str, pl.DataFrame],
    ) -> str | None:
        """生成缓存键

        基于 因子名 + config + 数据指纹（shape + 首尾值哈希）
        """
        try:
            import hashlib

            parts = [name]
            if config:
                parts.append(str(sorted(config.items())))

            # 数据指纹：shape + 首尾行哈希
            for key in sorted(data.keys()):
                df = data[key]
                shape = df.shape
                # 首尾各取一行做哈希（快速且区分度高）
                first_row = str(df.row(0)) if df.height > 0 else "empty"
                last_row = str(df.row(-1)) if df.height > 0 else "empty"
                parts.append(f"{key}:{shape}:{first_row}:{last_row}")

            key_str = "|".join(parts)
            return hashlib.md5(key_str.encode("utf-8")).hexdigest()
        except Exception:
            return None


# 全局单例
_library: FactorLibrary | None = None


def get_factor_library() -> FactorLibrary:
    """获取全局因子库单例"""
    global _library
    if _library is None:
        _library = FactorLibrary()
    return _library


__all__ = ["FactorLibrary", "get_factor_library"]
