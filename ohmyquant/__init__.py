"""OhMyQuant — Because quant trading shouldn't be a headache.

Plugins, backtesting, factors, and rebalancing, all in one swoop.

综合性量化框架，集成:
  - 量化策略迭代与版本管理
  - 回测引擎（多池、向量化）
  - 因子开发平台（定义→测试→优化→迭代）
  - 建仓调仓系统（成本收益权衡）
  - 策略插件系统（8 种可插拔组件）
  - 策略对比与统计显著性检验
"""
from __future__ import annotations

__version__ = "0.1.0"

from .core import (
    PluginRegistry,
    PluginType,
    get_config_manager,
    get_logger,
    register_allocator,
    register_cost_model,
    register_data_source,
    register_factor,
    register_risk_manager,
    register_rebalancer,
    register_scheduler,
    register_selector,
    setup_logging,
)


def _load_builtin_plugins() -> None:
    """发现并注册所有内置插件包（零配置热插拔）。

    各插件包的 __init__.py 调用 discover_modules(__name__) 自扫描子模块，
    新增插件只需把 .py 放进对应包即可被自动注册。
    """
    PluginRegistry.discover_builtin()


_load_builtin_plugins()

__all__ = [
    "__version__",
    "setup_logging",
    "get_logger",
    "PluginType",
    "PluginRegistry",
    "register_factor",
    "register_selector",
    "register_risk_manager",
    "register_allocator",
    "register_rebalancer",
    "register_data_source",
    "register_cost_model",
    "register_scheduler",
    "get_config_manager",
]
