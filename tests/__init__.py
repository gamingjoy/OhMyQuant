"""测试模块

提供 OhMyQuant 的测试套件：
  - 核心模块测试
  - 策略模块测试
  - 分析模块测试
  - 回测模块测试

运行测试：
  pytest tests/ -v
"""
from .test_core import TestPluginSystem, TestConfigLoader
from .test_strategy import TestStrategyBase, TestStrategyRegistry, TestVersionManager
from .test_analysis import TestMetrics, TestStrategyComparator, TestSignificanceTester
from .test_backtest import TestCostModel, TestExecutor, TestBacktestEngine

__all__ = [
    # 核心测试
    "TestPluginSystem",
    "TestConfigLoader",
    # 策略测试
    "TestStrategyBase",
    "TestStrategyRegistry",
    "TestVersionManager",
    # 分析测试
    "TestMetrics",
    "TestStrategyComparator",
    "TestSignificanceTester",
    # 回测测试
    "TestCostModel",
    "TestExecutor",
    "TestBacktestEngine",
]
