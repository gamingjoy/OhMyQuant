"""Plotly 可视化

提供策略回测的交互式图表：
  - 净值曲线
  - 回撤曲线
  - 收益分布
  - 因子 IC 曲线
  - 权重堆叠图
  - 分位数收益图

所有图表使用统一主题配置，支持导出为 HTML。
"""
from __future__ import annotations

import numpy as np

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
except ImportError:
    go = None
    px = None
    make_subplots = None

from ..core.logging import get_logger

logger = get_logger(__name__)


def plot_nav(returns, benchmark_returns=None, title="净值曲线"):
    """绘制净值曲线

    Args:
        returns: 每日收益序列
        benchmark_returns: 基准收益序列（可选）
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    nav = np.cumprod(1 + returns)

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=nav, mode="lines", name="策略"))

    if benchmark_returns is not None:
        bench_nav = np.cumprod(1 + benchmark_returns[: len(returns)])
        fig.add_trace(go.Scatter(y=bench_nav, mode="lines", name="基准"))

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="净值",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def plot_drawdown(returns, title="回撤曲线"):
    """绘制回撤曲线

    Args:
        returns: 每日收益序列
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    nav = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(nav)
    drawdown = (nav - running_max) / running_max

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=drawdown, mode="lines", fill="tozeroy", name="回撤"))

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="回撤",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def plot_returns_dist(returns, title="收益分布"):
    """绘制收益分布

    Args:
        returns: 每日收益序列
        title: 图表标题

    Returns:
        plotly figure
    """
    if px is None:
        logger.warning("需要安装 plotly")
        return None

    fig = px.histogram(returns, nbins=50, title=title)
    fig.update_layout(
        xaxis_title="日收益",
        yaxis_title="频率",
        template="plotly_white",
    )

    return fig


def plot_ic(ic_values, title="因子 IC"):
    """绘制因子 IC 曲线

    Args:
        ic_values: IC 值序列
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=ic_values, mode="lines", name="IC"))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="IC",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def plot_weights(weights_dict, title="权重堆叠图"):
    """绘制权重堆叠图

    Args:
        weights_dict: {股票代码: 权重序列}
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    fig = go.Figure()

    for code, weights in weights_dict.items():
        fig.add_trace(go.Scatter(y=weights, mode="lines", fill="tonexty", name=code))

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="权重",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def plot_quantile_returns(quantile_returns, title="分位数收益"):
    """绘制分位数收益

    Args:
        quantile_returns: {分位数: 收益序列}
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    fig = go.Figure()

    for quantile, returns in quantile_returns.items():
        nav = np.cumprod(1 + returns)
        fig.add_trace(go.Scatter(y=nav, mode="lines", name=f"分位数 {quantile}"))

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="净值",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def plot_correlation_matrix(corr_matrix, title="相关性矩阵"):
    """绘制相关性矩阵热图

    Args:
        corr_matrix: 相关性矩阵（polars DataFrame）
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    names = [c for c in corr_matrix.columns if c != "strategy"]
    corr_data = corr_matrix.drop("strategy").to_numpy()

    fig = go.Figure(
        data=go.Heatmap(
            z=corr_data,
            x=names,
            y=names,
            colorscale="RdBu",
            zmin=-1,
            zmax=1,
        )
    )

    fig.update_layout(
        title=title,
        template="plotly_white",
    )

    return fig


def plot_metrics(metrics_dict, title="绩效指标对比"):
    """绘制绩效指标对比图

    Args:
        metrics_dict: {策略名: PerformanceMetrics}
        title: 图表标题

    Returns:
        plotly figure
    """
    if go is None:
        logger.warning("需要安装 plotly")
        return None

    strategies = list(metrics_dict.keys())
    sharpe_ratios = [m.sharpe_ratio for m in metrics_dict.values()]
    returns = [m.annualized_return for m in metrics_dict.values()]
    vols = [m.annualized_volatility for m in metrics_dict.values()]
    drawdowns = [abs(m.max_drawdown) for m in metrics_dict.values()]

    fig = make_subplots(rows=2, cols=2, subplot_titles=("年化收益", "年化波动率", "Sharpe 比率", "最大回撤"))

    fig.add_trace(go.Bar(x=strategies, y=returns, name="年化收益"), row=1, col=1)
    fig.add_trace(go.Bar(x=strategies, y=vols, name="年化波动率"), row=1, col=2)
    fig.add_trace(go.Bar(x=strategies, y=sharpe_ratios, name="Sharpe 比率"), row=2, col=1)
    fig.add_trace(go.Bar(x=strategies, y=drawdowns, name="最大回撤"), row=2, col=2)

    fig.update_layout(title=title, template="plotly_white", showlegend=False)

    return fig


def export_html(fig, filename="plot.html"):
    """导出图表为 HTML

    Args:
        fig: plotly figure
        filename: 输出文件名
    """
    if fig is None:
        return
    import plotly.io as pio
    pio.write_html(fig, filename)
    logger.info(f"图表已导出: {filename}")


__all__ = [
    "plot_nav",
    "plot_drawdown",
    "plot_returns_dist",
    "plot_ic",
    "plot_weights",
    "plot_quantile_returns",
    "plot_correlation_matrix",
    "plot_metrics",
    "export_html",
]
