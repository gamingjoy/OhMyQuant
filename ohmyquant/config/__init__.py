"""配置模块

提供 OhMyQuant 的配置管理功能：
  - 默认配置
  - 配置加载器
  - 配置合并

用法：
    from ohmyquant.config import ConfigLoader, DEFAULT_CONFIG

    loader = ConfigLoader("config.yaml")
    backtest_config = loader.get_backtest_config()
"""
from .default_config import DEFAULT_CONFIG, ConfigLoader

__all__ = ["DEFAULT_CONFIG", "ConfigLoader"]
