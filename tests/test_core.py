"""核心模块测试

测试核心功能：
  - 插件系统
  - 配置管理
  - 日志系统
"""
import pytest

from ohmyquant.core.plugin_system import PluginRegistry, PluginType, register_strategy
from ohmyquant.config import ConfigLoader, DEFAULT_CONFIG


class TestPluginSystem:
    """插件系统测试"""

    def test_register_and_get(self):
        """测试注册和获取插件"""
        @register_strategy("test_strategy", "v1")
        class TestStrategy:
            pass

        plugin = PluginRegistry.get(PluginType.STRATEGY, "test_strategy_v1")
        assert plugin == TestStrategy

    def test_register_decorator(self):
        """测试注册装饰器"""
        @register_strategy("another_strategy", "v1")
        class AnotherStrategy:
            pass

        plugins = PluginRegistry.list_plugins(PluginType.STRATEGY)
        assert "another_strategy_v1" in plugins

    def test_list_plugins(self):
        """测试列出插件"""
        plugins = PluginRegistry.list_plugins(PluginType.STRATEGY)
        assert isinstance(plugins, list)


class TestConfigLoader:
    """配置加载器测试"""

    def test_default_config(self):
        """测试默认配置"""
        loader = ConfigLoader()
        assert loader.get("global.project_name") == "OhMyQuant"
        assert loader.get("backtest.initial_capital") == 1000000.0

    def test_config_get(self):
        """测试配置获取"""
        loader = ConfigLoader()
        assert loader.get("nonexistent.key", "default") == "default"

    def test_config_set(self):
        """测试配置设置"""
        loader = ConfigLoader()
        loader.set("test.key", "value")
        assert loader.get("test.key") == "value"

    def test_get_backtest_config(self):
        """测试获取回测配置"""
        loader = ConfigLoader()
        config = loader.get_backtest_config()
        assert "start_date" in config
        assert "end_date" in config
        assert "initial_capital" in config

    def test_get_strategy_config(self):
        """测试获取策略配置"""
        loader = ConfigLoader()
        config = loader.get_strategy_config()
        assert "default_strategy" in config
        assert "max_positions" in config
