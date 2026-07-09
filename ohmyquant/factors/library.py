"""因子库管理

提供因子注册、查找、批量计算等便捷功能。
"""
from __future__ import annotations

import polars as pl

from ..core.logging import get_logger
from .base import Factor, FactorRegistry

logger = get_logger(__name__)


class FactorLibrary:
    """因子库

    管理所有已注册因子，提供批量计算和查询功能。

    用法:
        lib = FactorLibrary()
        print(lib.list_factors())
        print(lib.list_factors(category="momentum"))
        results = lib.compute_factors(["mom_1m", "vol_20d"], ohlcv_data)
    """

    def __init__(self):
        # 确保内置因子已注册
        from . import builtin  # noqa: F401

    def list_factors(self, category: str | None = None) -> list[str]:
        """列出所有因子"""
        return FactorRegistry.list_factors(category)

    def list_categories(self) -> list[str]:
        """列出所有因子类别"""
        return FactorRegistry.list_categories()

    def get_factor_info(self, name: str) -> dict:
        """获取因子信息"""
        factor = FactorRegistry.create(name)
        return factor.get_info()

    def compute_factors(
        self,
        factor_names: list[str],
        data: dict[str, pl.DataFrame],
    ) -> dict[str, pl.DataFrame]:
        """批量计算多个因子

        Args:
            factor_names: 因子名列表
            data: 数据字典

        Returns:
            {factor_name: factor_values}
        """
        results = {}
        for name in factor_names:
            try:
                factor = FactorRegistry.create(name)
                results[name] = factor.compute(data)
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


# 全局单例
_library: FactorLibrary | None = None


def get_factor_library() -> FactorLibrary:
    """获取全局因子库单例"""
    global _library
    if _library is None:
        _library = FactorLibrary()
    return _library


__all__ = ["FactorLibrary", "get_factor_library"]
