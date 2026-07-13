"""测试配置

提供测试用的配置和 fixtures：
  - 配置加载器 fixture
  - 策略注册 fixture
  - 测试数据 fixture
"""
import numpy as np
import pytest

from ohmyquant.config import ConfigLoader
from ohmyquant.core.plugin_system import PluginRegistry, PluginType, register_strategy
from ohmyquant.strategy.base import BaseStrategy


@pytest.fixture(scope="session")
def config_loader():
    """配置加载器 fixture"""
    return ConfigLoader()


@pytest.fixture(scope="session")
def sample_returns():
    """示例收益数据 fixture"""
    return np.array([0.01, 0.02, -0.01, 0.03, 0.005, -0.008, 0.015, 0.02])


@pytest.fixture(scope="session")
def sample_strategies(sample_returns):
    """示例策略数据 fixture"""
    return {
        "strategy_a": sample_returns,
        "strategy_b": sample_returns * 0.8,
        "strategy_c": sample_returns * 1.2,
    }


@pytest.fixture(scope="function")
def clean_plugin_registry():
    """清理插件注册表 fixture"""
    original_plugins = PluginRegistry._plugins.copy()
    
    yield
    
    PluginRegistry._plugins = original_plugins


@pytest.fixture(scope="function")
def test_strategy():
    """测试策略 fixture"""
    @register_strategy("test_strategy", "v1")
    class TestStrategy(BaseStrategy):
        def run(self):
            return {"status": "success"}
        
        def get_latest_positions(self):
            return {"000001.SZ": 0.1, "000002.SZ": 0.05}
        
        @classmethod
        def from_version(cls, strategy_type, version, config=None):
            return cls(config or {})

    return TestStrategy
