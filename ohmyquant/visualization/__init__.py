"""可视化模块

提供策略回测的交互式可视化功能：
  - 净值曲线、回撤曲线、收益分布
  - 因子 IC 曲线、权重堆叠图、分位数收益图
  - 相关性矩阵热图、绩效指标对比图
  - 交互仪表盘（支持策略选择、指标切换）
  - 主题配置（浅色/深色/专业/彩色）

用法：
    from ohmyquant.visualization import plot_nav, plot_drawdown, StrategyDashboard

    fig = plot_nav(daily_returns)
    fig.show()

    dashboard = StrategyDashboard({"策略A": returns_a, "策略B": returns_b})
    dashboard.generate_dashboard()
"""
from .dashboard import StrategyDashboard
from .plots import (
    export_html,
    plot_correlation_matrix,
    plot_drawdown,
    plot_ic,
    plot_metrics,
    plot_nav,
    plot_quantile_returns,
    plot_returns_dist,
    plot_weights,
)
from .themes import ThemeConfig, ThemeManager, get_theme, set_theme

__all__ = [
    # 可视化图表
    "plot_nav",
    "plot_drawdown",
    "plot_returns_dist",
    "plot_ic",
    "plot_weights",
    "plot_quantile_returns",
    "plot_correlation_matrix",
    "plot_metrics",
    "export_html",
    # 仪表盘
    "StrategyDashboard",
    # 主题配置
    "ThemeConfig",
    "ThemeManager",
    "set_theme",
    "get_theme",
]
