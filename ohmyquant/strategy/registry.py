"""策略注册表

管理策略版本和运行时注册，使用 lru_cache 缓存策略类以提高性能。

设计目标：
  - 支持运行时动态注册策略
  - 支持通过版本号加载策略类
  - 使用 lru_cache 缓存已加载的策略类
  - 与 PluginRegistry 集成
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable

from ..core.logging import get_logger
from ..core.plugin_system import PluginRegistry, PluginType
from .base import BaseStrategy
from .version_manager import VersionManager

logger = get_logger(__name__)


class StrategyRegistry:
    """策略注册表

    使用 lru_cache 缓存策略类，避免重复导入。
    """

    @classmethod
    @lru_cache(maxsize=128)
    def get_strategy_class(cls, strategy_type: str, version: str) -> type:
        """获取策略类（缓存）

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2）

        Returns:
            type: 策略类

        Raises:
            ValueError: 策略不存在
        """
        # VersionManager.import_strategy_class 内部先查 PluginRegistry，再回退到动态导入
        try:
            return VersionManager.import_strategy_class(strategy_type, version)
        except Exception as e:
            logger.error(f"获取策略类失败: {strategy_type} {version}, 错误: {e}")
            raise ValueError(f"策略不存在: {strategy_type} {version}") from e

    @classmethod
    def register_strategy(cls, strategy_type: str, version: str) -> Callable[[type], type]:
        """装饰器：注册策略类

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2）

        Returns:
            Callable[[type], type]: 装饰器函数

        Usage:
            @StrategyRegistry.register_strategy("ycj", "v1")
            class YCJStrategyV1(BaseStrategy):
                ...
        """

        def decorator(klass: type) -> type:
            plugin_name = f"{strategy_type}_{version}"
            PluginRegistry.register(PluginType.STRATEGY, plugin_name)(klass)
            logger.info(f"策略已注册: {strategy_type} {version} → {klass.__name__}")
            return klass

        return decorator

    @classmethod
    def create(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> BaseStrategy:
        """创建策略实例

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2）
            config: 运行时配置覆盖

        Returns:
            BaseStrategy: 策略实例
        """
        strategy_class = cls.get_strategy_class(strategy_type, version)

        # 加载基础配置
        base_config = VersionManager.load_config(strategy_type, version)

        # 合并配置
        if config:
            base_config.update(config)

        return strategy_class(base_config)

    @classmethod
    def list_strategies(cls) -> list[dict[str, Any]]:
        """列出所有可用策略

        Returns:
            list[dict[str, Any]]: 策略信息列表
        """
        strategies: list[dict[str, Any]] = []
        for strategy_type in VersionManager.list_strategy_types():
            for version in VersionManager.list_versions(strategy_type):
                try:
                    strategy_class = cls.get_strategy_class(strategy_type, version)
                    description = getattr(strategy_class, "__doc__", "") or ""
                except Exception:
                    description = ""
                strategies.append(
                    {
                        "strategy_type": strategy_type,
                        "version": version,
                        "description": description,
                    }
                )
        return strategies

    @classmethod
    def clear_cache(cls) -> None:
        """清除缓存"""
        cls.get_strategy_class.cache_clear()
        logger.info("策略注册表缓存已清除")


__all__ = ["StrategyRegistry"]
