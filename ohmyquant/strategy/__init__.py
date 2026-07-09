"""策略系统

提供策略版本管理、注册表和统一运行入口。

核心组件：
  - BaseStrategy: 策略抽象基类
  - StrategyRegistry: 策略注册表（lru_cache）
  - VersionManager: 版本管理器（动态导入）
  - StrategyRunner: 策略运行器（统一入口）

策略命名约定：
  - YCJ_strategy: 量化策略（因子驱动）
  - DH_strategy: 人工策略（规则驱动）

用法：
    # 方式1：直接运行
    from ohmyquant.strategy import run
    result = run("ycj", "v1", backtest={"start_date": "2024-01-01"})

    # 方式2：创建运行器
    from ohmyquant.strategy import StrategyRunner
    runner = StrategyRunner(config)
    result = runner.run()

    # 方式3：从版本创建策略
    from ohmyquant.strategy import StrategyRegistry
    strategy = StrategyRegistry.create("ycj", "v1")
    result = strategy.run()
"""
from .base import BaseStrategy, StrategyInfo, register_strategy
from .registry import StrategyRegistry
from .runner import StrategyResult, StrategyRunner, run
from .version_manager import VersionManager

# 导入策略子包以触发 @register_strategy 装饰器注册
from . import strategies  # noqa: F401

__all__ = [
    "BaseStrategy",
    "StrategyInfo",
    "StrategyRegistry",
    "StrategyRunner",
    "StrategyResult",
    "VersionManager",
    "register_strategy",
    "run",
]
