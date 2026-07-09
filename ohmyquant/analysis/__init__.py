"""分析模块

提供策略绩效分析、多策略对比、统计显著性检验和归因分析。

核心组件：
  - PerformanceMetrics: 绩效指标数据类
  - StrategyComparator: 多策略对比器
  - SignificanceTester: 统计显著性测试器
  - PositionAttributor/FactorAttributor/TimeAttributor: 归因分析器
  - ReportGenerator: 报告生成器

用法：
    from ohmyquant.analysis import compute_metrics, StrategyComparator

    metrics = compute_metrics(daily_returns)
    comparator = StrategyComparator({"策略A": returns_a, "策略B": returns_b})
    table = comparator.get_comparison_table()
"""
from .attribution import FactorAttributor, PositionAttributor, TimeAttributor
from .compare import StrategyComparator
from .metrics import (
    PerformanceMetrics,
    compute_annualized_return,
    compute_annualized_volatility,
    compute_calmar_ratio,
    compute_cvar,
    compute_info_ratio,
    compute_kurtosis,
    compute_max_drawdown,
    compute_metrics,
    compute_profit_factor,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_skewness,
    compute_total_return,
    compute_var,
    compute_win_rate,
    print_metrics,
)
from .report import ReportGenerator
from .significance import SignificanceResult, SignificanceTester

__all__ = [
    # 绩效指标
    "PerformanceMetrics",
    "compute_total_return",
    "compute_annualized_return",
    "compute_annualized_volatility",
    "compute_sharpe_ratio",
    "compute_sortino_ratio",
    "compute_max_drawdown",
    "compute_calmar_ratio",
    "compute_var",
    "compute_cvar",
    "compute_skewness",
    "compute_kurtosis",
    "compute_win_rate",
    "compute_profit_factor",
    "compute_info_ratio",
    "compute_metrics",
    "print_metrics",
    # 多策略对比
    "StrategyComparator",
    # 统计显著性
    "SignificanceResult",
    "SignificanceTester",
    # 归因分析
    "PositionAttributor",
    "FactorAttributor",
    "TimeAttributor",
    # 报告生成
    "ReportGenerator",
]
