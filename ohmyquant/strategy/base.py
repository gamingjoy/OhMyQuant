"""策略基类

定义策略抽象接口，所有策略实现必须继承此类。

策略系统设计：
  - BaseStrategy ABC：定义标准接口（run/from_version/get_latest_positions/get_config_summary）
  - StrategyRegistry：版本注册表，通过 lru_cache 缓存策略类
  - VersionManager：动态导入策略模块（支持迭代版本）
  - StrategyRunner：统一运行入口

用法：
    from ohmyquant.strategy import BaseStrategy, register_strategy

    @register_strategy("ycj", "v1")
    class YCJStrategyV1(BaseStrategy):
        def run(self):
            ...
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..core.config_models import StrategyConfig
from ..core.logging import get_logger
from ..core.plugin_system import register_strategy as _register_strategy
from ..engine.base import BacktestResult

logger = get_logger(__name__)


@dataclass
class StrategyInfo:
    """策略信息"""

    strategy_type: str
    version: str
    description: str = ""
    author: str = ""
    created_at: str = ""
    tags: list[str] = field(default_factory=list)


class BaseStrategy(ABC):
    """策略抽象基类

    所有策略实现必须继承此类并实现抽象方法。

    核心接口：
        - from_version(strategy_type, version, config): 工厂方法，创建策略实例
        - run(): 执行策略，返回回测结果（默认实现：通过 StrategyRunner 运行）
        - get_latest_positions(): 获取最新持仓（默认实现：返回空）
        - get_config_summary(): 获取配置摘要
    """

    def __init__(self, config: StrategyConfig | dict):
        if isinstance(config, dict):
            self.config = StrategyConfig(**config)
        else:
            self.config = config

    def run(self) -> BacktestResult:
        """执行策略（默认实现：通过 StrategyRunner 运行回测）

        子类通常无需重写此方法，只需在 from_version 中提供配置即可。

        Returns:
            BacktestResult: 回测结果
        """
        from .runner import StrategyRunner

        runner = StrategyRunner(self.config)
        result = runner.run()
        return result.backtest_result

    def get_latest_positions(self) -> dict[str, float]:
        """获取最新持仓

        默认返回空字典。子类可在实现持仓信号逻辑后重写。

        Returns:
            dict[str, float]: {code: weight} 持仓权重
        """
        return {}

    def get_config_summary(self) -> dict[str, Any]:
        """获取配置摘要

        Returns:
            dict[str, Any]: 配置摘要字典
        """
        return {
            "strategy_type": self.config.strategy_type,
            "strategy_version": self.config.strategy_version,
            "strategy_name": self.config.strategy_name,
            "description": self.config.description,
            "backtest": {
                "start_date": self.config.backtest.start_date,
                "end_date": self.config.backtest.end_date,
            },
            "selection": {
                "method": self.config.selection.method,
                "top_n": self.config.selection.top_n,
            },
            "risk": {
                "target_vol": self.config.risk.target_vol,
            },
            "allocation": {
                "method": self.config.allocation.method,
            },
            "rebalance": {
                "frequency": self.config.rebalance.frequency,
                "method": self.config.rebalance.method,
            },
        }

    @classmethod
    @abstractmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "BaseStrategy":
        """工厂方法：从版本创建策略实例

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2）
            config: 运行时配置覆盖

        Returns:
            BaseStrategy: 策略实例
        """
        ...


def register_strategy(strategy_type: str, version: str):
    """装饰器：注册策略类

    Args:
        strategy_type: 策略类型（ycj/dh）
        version: 版本号（v1/v2）

    Usage:
        @register_strategy("ycj", "v1")
        class YCJStrategyV1(BaseStrategy):
            ...
    """
    return _register_strategy(strategy_type, version)


__all__ = [
    "BaseStrategy",
    "StrategyInfo",
    "register_strategy",
]
