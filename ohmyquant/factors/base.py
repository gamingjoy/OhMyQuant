"""因子平台核心

Factor ABC 定义因子接口，FactorRegistry 管理因子注册。
因子开发工作流：定义 → 测试 → 优化 → 迭代
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from ..core.logging import get_logger
from ..core.plugin_system import PluginRegistry, PluginType, register_factor

logger = get_logger(__name__)


class Factor(ABC):
    """因子抽象基类

    子类需要:
      1. 设置类属性: name, category, direction, required_fields
      2. 实现 compute() 方法

    direction:
      1 = 正向（因子值大 → 预期收益高）
      -1 = 反向（因子值小 → 预期收益高）

    用法:
        @register_factor("mom_1m", category="momentum")
        class Momentum1M(Factor):
            name = "mom_1m"
            category = "momentum"
            direction = 1
            required_fields = ["close"]

            def compute(self, data):
                close = data["close"]
                # 返回 date × code 的因子值矩阵
                ...
    """

    # 因子元数据（子类覆盖）
    name: str = ""
    category: str = ""
    description: str = ""
    direction: int = 1  # 1=正向, -1=反向
    required_fields: list[str] = []

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        """计算因子值

        Args:
            data: 数据字典 {"close": wide_df, "volume": wide_df, ...}
                  wide_df 格式: date 为行索引, code 为列

        Returns:
            date × code 的因子值矩阵（与输入相同的宽表格式）
        """
        ...

    def get_direction(self) -> int:
        """返回因子方向"""
        return self.direction

    def get_info(self) -> dict[str, Any]:
        """返回因子信息"""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "direction": self.direction,
            "required_fields": self.required_fields,
        }


class FactorRegistry:
    """因子注册表（基于 PluginRegistry）"""

    @staticmethod
    def register(name: str | None = None, category: str = ""):
        """注册因子装饰器"""
        return register_factor(name, category=category)

    @staticmethod
    def get(name: str) -> type[Factor]:
        """获取因子类"""
        return PluginRegistry.get(PluginType.FACTOR, name)

    @staticmethod
    def create(name: str, config: dict | None = None) -> Factor:
        """创建因子实例"""
        return PluginRegistry.create(PluginType.FACTOR, name, config=config)

    @staticmethod
    def list_factors(category: str | None = None) -> list[str]:
        """列出已注册的因子"""
        return PluginRegistry.list_plugins(PluginType.FACTOR, category=category)

    @staticmethod
    def list_categories() -> list[str]:
        """列出所有因子类别"""
        registry = PluginRegistry._registries.get(PluginType.FACTOR, {})
        categories = set()
        for _, meta in registry.values():
            if meta.category:
                categories.add(meta.category)
        return sorted(categories)


def compute_factor(
    factor_name: str,
    data: dict[str, pl.DataFrame],
    config: dict | None = None,
) -> pl.DataFrame:
    """便捷函数：计算指定因子

    Args:
        factor_name: 因子注册名
        data: 数据字典
        config: 因子配置

    Returns:
        因子值矩阵 (date × code)
    """
    factor = FactorRegistry.create(factor_name, config)
    return factor.compute(data)


__all__ = [
    "Factor",
    "FactorRegistry",
    "compute_factor",
    "register_factor",
]
