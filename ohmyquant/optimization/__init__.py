"""策略优化与集成

提供信号生成框架、walk-forward 优化、参数搜索和多策略集成。

核心组件:
  - Signal: 信号抽象基类（FactorSignal/CompositeSignal/ModelSignal）
  - StrategyWalkForward: 策略级 walk-forward 优化
  - ParamSearcher: Optuna 参数搜索
  - StrategyEnsemble: 多策略集成
"""
from __future__ import annotations

from .signal import (
    CompositeSignal,
    FactorSignal,
    ModelSignal,
    Signal,
)
from .walk_forward import StrategyWalkForward, WalkForwardReport
from .param_search import OptimizationReport, ParamSearcher
from .ensemble import EnsembleResult, StrategyEnsemble

__all__ = [
    "Signal",
    "FactorSignal",
    "CompositeSignal",
    "ModelSignal",
    "StrategyWalkForward",
    "WalkForwardReport",
    "ParamSearcher",
    "OptimizationReport",
    "StrategyEnsemble",
    "EnsembleResult",
]
