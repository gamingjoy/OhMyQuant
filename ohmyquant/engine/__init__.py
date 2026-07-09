"""回测引擎模块

提供完整的回测引擎，整合选股器、风控管理器、分配器、组合优化器。
"""
from .allocator import BaseAllocator
from .allocators import (
    EqualAllocator,
    HRPAllocator,
    ICIRWeightedAllocator,
    create_allocator,
)
from .base import BacktestResult, BaseEngine
from .context import BacktestContext
from .portfolio import PortfolioOptimizer
from .risk import BaseRiskManager
from .risk_managers import (
    CVaRRiskManager,
    DrawdownDefenseRiskManager,
    RegimeAdaptiveRiskManager,
    VolTargetRiskManager,
    create_risk_manager,
)
from .selector import BaseSelector
from .selectors import (
    AdaptiveICIRSelector,
    HybridSelector,
    ICIRSelector,
    create_selector,
)
from .backtest import BacktestEngine

__all__ = [
    # 基类
    "BacktestResult",
    "BaseEngine",
    "BacktestContext",
    "BaseSelector",
    "BaseRiskManager",
    "BaseAllocator",
    # 选股器
    "create_selector",
    "ICIRSelector",
    "HybridSelector",
    "AdaptiveICIRSelector",
    # 风控管理器
    "create_risk_manager",
    "VolTargetRiskManager",
    "CVaRRiskManager",
    "DrawdownDefenseRiskManager",
    "RegimeAdaptiveRiskManager",
    # 分配器
    "create_allocator",
    "EqualAllocator",
    "HRPAllocator",
    "ICIRWeightedAllocator",
    # 组合优化器
    "PortfolioOptimizer",
    # 主引擎
    "BacktestEngine",
]
