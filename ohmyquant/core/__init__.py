"""OhMyQuant 核心基础设施"""
from .config_manager import ConfigManager, get_config_manager
from .config_models import (
    AllocationConfig,
    BacktestConfig,
    DataConfig,
    PortfolioConfig,
    RebalanceConfig,
    RiskConfig,
    SelectionConfig,
    StrategyConfig,
)
from .exceptions import (
    BacktestError,
    ConfigError,
    DataNotFoundError,
    DataSourceError,
    FactorError,
    OhMyQuantError,
    PluginLoadError,
    PluginNotFoundError,
    RebalanceError,
    StrategyError,
    StrategyVersionNotFoundError,
    ValidationError,
)
from .logging import get_logger, logger, setup_logging
from .plugin_system import (
    PluginMeta,
    PluginRegistry,
    PluginType,
    register_allocator,
    register_cost_model,
    register_data_source,
    register_factor,
    register_risk_manager,
    register_rebalancer,
    register_scheduler,
    register_selector,
)

__all__ = [
    # Logging
    "setup_logging",
    "get_logger",
    "logger",
    # Exceptions
    "OhMyQuantError",
    "ConfigError",
    "PluginNotFoundError",
    "PluginLoadError",
    "DataSourceError",
    "DataNotFoundError",
    "StrategyError",
    "StrategyVersionNotFoundError",
    "BacktestError",
    "FactorError",
    "RebalanceError",
    "ValidationError",
    # Plugin system
    "PluginType",
    "PluginMeta",
    "PluginRegistry",
    "register_factor",
    "register_selector",
    "register_risk_manager",
    "register_allocator",
    "register_rebalancer",
    "register_data_source",
    "register_cost_model",
    "register_scheduler",
    # Config
    "ConfigManager",
    "get_config_manager",
    "StrategyConfig",
    "BacktestConfig",
    "SelectionConfig",
    "RiskConfig",
    "AllocationConfig",
    "PortfolioConfig",
    "DataConfig",
    "RebalanceConfig",
]
