"""因子平台

提供因子定义、测试、优化和迭代的完整工作流。

工作流:
  1. 定义因子: 继承 Factor ABC，用 @register_factor 注册
  2. 测试因子: FactorTester.test_factor() 计算 IC/ICIR/分位数
  3. 优化组合: FactorOptimizer.select_strong_factors() 筛选强因子
  4. 迭代: 基于测试结果调整因子参数和组合
"""
from . import builtin  # noqa: F401  注册内置因子
from .analysis import FactorAnalyzer, FactorStats, QuantileAnalysis, compute_all_returns
from .base import Factor, FactorRegistry, compute_factor, register_factor
from .library import FactorLibrary, get_factor_library
from .optimizer import FactorOptimizer
from .testing import FactorTester, FactorTestResult

__all__ = [
    "Factor",
    "FactorRegistry",
    "register_factor",
    "compute_factor",
    "FactorAnalyzer",
    "FactorStats",
    "QuantileAnalysis",
    "compute_all_returns",
    "FactorTester",
    "FactorTestResult",
    "FactorOptimizer",
    "FactorLibrary",
    "get_factor_library",
]
