"""因子平台核心

Factor ABC 定义因子接口，FactorRegistry 管理因子注册。
因子开发工作流：定义 → 测试 → 优化 → 迭代

特性:
  - 参数化因子: 通过 params 字典声明可配置参数，运行时用 config 覆盖
  - 因子缓存: FactorLibrary 支持 LRU 缓存避免重复计算
  - 外部因子: 支持从外部目录加载自定义因子
  - 因子依赖: depends_on 声明依赖，自动先计算依赖因子
  - 版本管理: version 属性支持因子迭代
"""
from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from pathlib import Path
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

    可选类属性:
      - params: 可配置参数字典（窗口期、阈值等），运行时用 config 覆盖
      - depends_on: 依赖的其他因子名列表，FactorLibrary 会自动先计算
      - version: 因子版本号，默认 "v1"

    direction:
      1 = 正向（因子值大 → 预期收益高）
      -1 = 反向（因子值小 → 预期收益高）

    用法:
        @register_factor()  # 自动从类属性读取 name, category
        class Momentum1M(Factor):
            name = "mom_1m"
            category = "momentum"
            direction = 1
            required_fields = ["close"]
            params = {"window": 20}  # 可配置参数

            def compute(self, data):
                return _pct_change(data["close"], self.params["window"])
    """

    # 因子元数据（子类覆盖）
    name: str = ""
    category: str = ""
    description: str = ""
    direction: int = 1  # 1=正向, -1=反向
    required_fields: list[str] = []

    # 可选扩展属性
    params: dict[str, Any] = {}  # 可配置参数（子类定义默认值，config 覆盖）
    depends_on: list[str] = []  # 依赖的其他因子名
    version: str = "v1"  # 因子版本

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        # 深拷贝 params 避免类属性被实例修改
        self.params = copy.deepcopy(self.params)
        # 用 config 覆盖 params 中的同名键
        for key, value in self.config.items():
            if key in self.params:
                self.params[key] = value
            elif key in ("name", "category", "direction"):
                # 允许 config 覆盖元数据
                setattr(self, key, value)

    def get_param(self, key: str, default: Any = None) -> Any:
        """获取参数值"""
        return self.params.get(key, default)

    @abstractmethod
    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        """计算因子值

        Args:
            data: 数据字典 {"close": wide_df, "volume": wide_df, ...}
                  wide_df 格式: date 为行索引, code 为列
                  如果因子声明了 depends_on，data 中会包含依赖因子的结果

        Returns:
            date × code 的因子值矩阵（与输入相同的宽表格式）
        """
        ...

    def get_direction(self) -> int:
        """返回因子方向"""
        return self.direction

    def get_info(self) -> dict[str, Any]:
        """返回因子完整信息"""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "direction": self.direction,
            "required_fields": self.required_fields,
            "params": self.params,
            "depends_on": self.depends_on,
            "version": self.version,
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

    @staticmethod
    def get_info(name: str) -> dict[str, Any]:
        """获取因子元数据"""
        klass = FactorRegistry.get(name)
        instance = klass()
        return instance.get_info()

    @staticmethod
    def discover_external(paths: list[str | Path]) -> int:
        """从外部目录加载因子模块

        扫描指定目录下的 .py 文件，导入并触发 @register_factor 装饰器。
        用于加载用户自定义因子，无需修改源码。

        Args:
            paths: 外部因子目录路径列表

        Returns:
            成功加载的模块数
        """
        import importlib.util
        import sys

        count = 0
        for path in paths:
            path = Path(path)
            if not path.is_dir():
                logger.warning(f"外部因子目录不存在: {path}")
                continue

            for py_file in sorted(path.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module_name = f"_external_factor_{py_file.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    count += 1
                    logger.info(f"加载外部因子: {py_file}")
                except Exception as e:
                    logger.warning(f"加载外部因子失败 {py_file}: {e}")

        return count


def compute_factor(
    factor_name: str,
    data: dict[str, pl.DataFrame],
    config: dict | None = None,
) -> pl.DataFrame:
    """便捷函数：计算指定因子

    Args:
        factor_name: 因子注册名
        data: 数据字典
        config: 因子配置（覆盖 params 默认值）

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
