"""统一异常体系

框架所有模块抛出的异常都继承自 OhMyQuantError，
便于上层统一捕获和处理。
"""
from __future__ import annotations


class OhMyQuantError(Exception):
    """框架基础异常"""


class ConfigError(OhMyQuantError):
    """配置错误（文件缺失、格式错误、校验失败）"""


class PluginNotFoundError(OhMyQuantError):
    """插件未找到"""

    def __init__(self, plugin_type: str, name: str, available: list[str] | None = None):
        msg = f"未找到插件 {plugin_type}/{name}"
        if available:
            msg += f"，可用: {available}"
        super().__init__(msg)
        self.plugin_type = plugin_type
        self.name = name
        self.available = available or []


class PluginLoadError(OhMyQuantError):
    """插件加载失败"""


class DataSourceError(OhMyQuantError):
    """数据源错误（连接失败、数据缺失）"""


class DataNotFoundError(DataSourceError):
    """请求的数据不存在"""


class StrategyError(OhMyQuantError):
    """策略错误（版本不存在、运行失败）"""


class StrategyVersionNotFoundError(StrategyError):
    """策略版本不存在"""

    def __init__(self, strategy_type: str, version: str, available: list[str] | None = None):
        msg = f"策略版本不存在: {strategy_type}/{version}"
        if available:
            msg += f"，可用版本: {available}"
        super().__init__(msg)
        self.strategy_type = strategy_type
        self.version = version


class BacktestError(OhMyQuantError):
    """回测错误"""


class FactorError(OhMyQuantError):
    """因子错误（计算失败、注册冲突）"""


class RebalanceError(OhMyQuantError):
    """调仓错误"""


class ValidationError(OhMyQuantError):
    """数据/参数校验错误"""
