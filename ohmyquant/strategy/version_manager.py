"""版本管理器

负责动态导入策略模块，支持主版本和迭代版本。

目录结构：
    strategies/
    ├── ycj/
    │   ├── v1/
    │   │   ├── __init__.py
    │   │   ├── config.yaml
    │   │   └── strategy.py
    │   └── v2/
    │       ├── __init__.py
    │       ├── config.yaml
    │       ├── strategy.py
    │       └── iterations/
    │           └── v2_1/
    │               ├── __init__.py
    │               └── config.yaml
    └── dh/
        └── v1/
            ├── __init__.py
            ├── config.yaml
            └── strategy.py

迭代版本映射：
    v2.1 → v2/iterations/v2_1/
    v2.2 → v2/iterations/v2_2/
"""
from __future__ import annotations

import importlib
import os
from typing import Any

from ..core.config_models import StrategyConfig
from ..core.logging import get_logger

logger = get_logger(__name__)

STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")


class VersionManager:
    """版本管理器

    负责动态导入策略模块和加载配置。
    """

    @staticmethod
    def get_module_path(strategy_type: str, version: str) -> str:
        """获取策略模块路径

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2/v2.1）

        Returns:
            str: 模块路径（如 "ohmyquant.strategy.strategies.ycj.v1.strategy"）

        Raises:
            ValueError: 版本格式无效
        """
        # 处理迭代版本（v2.1 → v2/iterations/v2_1）
        if "." in version:
            base_version, iteration = version.split(".", 1)
            module_path = f"ohmyquant.strategy.strategies.{strategy_type}.{base_version}.iterations.{base_version}_{iteration}.strategy"
        else:
            module_path = f"ohmyquant.strategy.strategies.{strategy_type}.{version}.strategy"

        return module_path

    @staticmethod
    def get_config_path(strategy_type: str, version: str) -> str:
        """获取配置文件路径

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2/v2.1）

        Returns:
            str: 配置文件路径
        """
        if "." in version:
            base_version, iteration = version.split(".", 1)
            config_path = os.path.join(
                STRATEGIES_DIR,
                strategy_type,
                base_version,
                "iterations",
                f"{base_version}_{iteration}",
                "config.yaml",
            )
        else:
            config_path = os.path.join(
                STRATEGIES_DIR, strategy_type, version, "config.yaml"
            )

        return config_path

    @staticmethod
    def import_strategy_class(strategy_type: str, version: str) -> type:
        """动态导入策略类

        优先从 PluginRegistry 查找（已由 discover_builtin 自动注册）；
        未命中再走 importlib 动态导入（用于尚未被发现的迭代版本）。

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2/v2.1）

        Returns:
            type: 策略类

        Raises:
            ModuleNotFoundError: 模块不存在
            AttributeError: 策略类不存在
        """
        # 优先走 PluginRegistry（discover_builtin 已注册所有 strategies/ 下策略）
        from ..core.plugin_system import PluginRegistry, PluginType

        plugin_name = f"{strategy_type}_{version}"
        try:
            return PluginRegistry.get(PluginType.STRATEGY, plugin_name)
        except Exception:
            pass  # 未注册（如迭代版本尚未被发现），回退到动态导入

        module_path = VersionManager.get_module_path(strategy_type, version)

        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            logger.error(f"策略模块不存在: {module_path}")
            raise

        # 查找策略类（策略类名格式：{StrategyType}Strategy{Version}）
        class_name = VersionManager._guess_class_name(strategy_type, version)
        if hasattr(module, class_name):
            return getattr(module, class_name)

        # 尝试查找 BaseStrategy 的子类
        from .base import BaseStrategy

        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, BaseStrategy) and obj != BaseStrategy:
                return obj

        raise AttributeError(f"策略类未找到: {module_path}")

    @staticmethod
    def _guess_class_name(strategy_type: str, version: str) -> str:
        """猜测策略类名

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2/v2.1）

        Returns:
            str: 类名（如 YCJStrategyV1）
        """
        type_map = {
            "ycj": "YCJ",
            "dh": "DH",
        }
        type_prefix = type_map.get(strategy_type.upper(), strategy_type.capitalize())

        # 版本号处理：v2.1 → V2_1
        version_clean = version.replace(".", "_").upper()

        return f"{type_prefix}Strategy{version_clean}"

    @staticmethod
    def load_config(strategy_type: str, version: str) -> dict[str, Any]:
        """加载策略配置

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2/v2.1）

        Returns:
            dict[str, Any]: 配置字典
        """
        config_path = VersionManager.get_config_path(strategy_type, version)

        if not os.path.exists(config_path):
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return {}

        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"加载配置文件失败: {config_path}, 错误: {e}")
            return {}

    @staticmethod
    def merge_config(
        base_config: dict[str, Any], overrides: dict[str, Any] | None = None
    ) -> StrategyConfig:
        """合并配置

        Args:
            base_config: 基础配置
            overrides: 运行时覆盖配置

        Returns:
            StrategyConfig: 合并后的配置
        """
        merged = dict(base_config)
        if overrides:
            merged.update(overrides)
        return StrategyConfig(**merged)

    @staticmethod
    def list_versions(strategy_type: str) -> list[str]:
        """列出策略类型的所有版本

        Args:
            strategy_type: 策略类型（ycj/dh）

        Returns:
            list[str]: 版本号列表
        """
        type_dir = os.path.join(STRATEGIES_DIR, strategy_type)
        if not os.path.exists(type_dir):
            return []

        versions: list[str] = []
        for item in os.listdir(type_dir):
            item_path = os.path.join(type_dir, item)
            if not os.path.isdir(item_path):
                continue

            # 主版本（v1, v2, ...）
            if item.startswith("v") and item[1:].isdigit():
                versions.append(item)

                # 迭代版本
                iterations_dir = os.path.join(item_path, "iterations")
                if os.path.exists(iterations_dir):
                    for iteration in os.listdir(iterations_dir):
                        it_path = os.path.join(iterations_dir, iteration)
                        if os.path.isdir(it_path):
                            # v2_1 → v2.1
                            if "_" in iteration:
                                base, it = iteration.split("_", 1)
                                full_version = f"{base}.{it}"
                                versions.append(full_version)

        return sorted(versions)

    @staticmethod
    def list_strategy_types() -> list[str]:
        """列出所有策略类型

        Returns:
            list[str]: 策略类型列表（ycj/dh）
        """
        if not os.path.exists(STRATEGIES_DIR):
            return []

        types: list[str] = []
        for item in os.listdir(STRATEGIES_DIR):
            item_path = os.path.join(STRATEGIES_DIR, item)
            if os.path.isdir(item_path) and not item.startswith("__"):
                types.append(item)

        return sorted(types)


__all__ = ["VersionManager"]
