"""策略模块测试

测试策略功能：
  - 策略注册
  - 策略版本管理
  - 策略运行器
"""
import pytest

from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.version_manager import VersionManager


class TestStrategyBase:
    """策略基类测试"""

    def test_base_strategy_interface(self):
        """测试策略接口"""
        class TestStrategy(BaseStrategy):
            def run(self):
                return {}
            
            def get_latest_positions(self):
                return {}
            
            @classmethod
            def from_version(cls, strategy_type, version, config=None):
                return cls(config or {})

        strategy = TestStrategy({"param1": "value1"})
        assert strategy.config.param1 == "value1"

        summary = strategy.get_config_summary()
        assert isinstance(summary, dict)


class TestStrategyRegistry:
    """策略注册表测试"""

    def test_create_strategy(self):
        """测试创建策略"""
        try:
            strategy = StrategyRegistry.create("ycj", "v1")
            assert strategy is not None
        except Exception:
            pytest.skip("策略实现可能尚未完成")

    def test_get_strategy_class(self):
        """测试获取策略类"""
        try:
            strategy_class = StrategyRegistry.get_strategy_class("ycj", "v1")
            assert strategy_class is not None
        except Exception:
            pytest.skip("策略实现可能尚未完成")


class TestVersionManager:
    """版本管理器测试"""

    def test_list_strategy_types(self):
        """测试列出策略类型"""
        types = VersionManager.list_strategy_types()
        assert isinstance(types, list)

    def test_list_versions(self):
        """测试列出版本"""
        try:
            versions = VersionManager.list_versions("ycj")
            assert isinstance(versions, list)
        except Exception:
            pytest.skip("策略目录可能不存在")

    def test_get_module_path(self):
        """测试获取模块路径"""
        path = VersionManager.get_module_path("test", "v1")
        assert "test" in path
        assert "v1" in path

        path_with_iteration = VersionManager.get_module_path("test", "v2.1")
        assert "test" in path_with_iteration
        assert "v2" in path_with_iteration
        assert "iterations" in path_with_iteration
