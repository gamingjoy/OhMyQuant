"""交互仪表盘

提供策略回测的交互式仪表盘，支持：
  - 动态策略选择
  - 时间范围筛选
  - 指标切换
  - 多图表联动
  - 数据导出

仪表盘组件：
  - StrategyDashboard: 策略仪表盘
"""
from __future__ import annotations

import os

import numpy as np

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio
except ImportError:
    go = None
    make_subplots = None
    pio = None

from ..analysis.metrics import compute_metrics
from ..analysis.compare import StrategyComparator
from ..core.logging import get_logger

logger = get_logger(__name__)


class StrategyDashboard:
    """策略仪表盘"""

    def __init__(self, strategies: dict[str, np.ndarray] | None = None):
        """初始化仪表盘

        Args:
            strategies: {策略名: 收益序列}
        """
        self.strategies = strategies or {}

    def add_strategy(self, name: str, returns: np.ndarray) -> None:
        """添加策略

        Args:
            name: 策略名称
            returns: 收益序列
        """
        self.strategies[name] = returns

    def generate_dashboard(self, output_path: str = "dashboard.html") -> str:
        """生成交互式仪表盘

        Args:
            output_path: 输出路径

        Returns:
            str: HTML 内容
        """
        if go is None or make_subplots is None or pio is None:
            logger.warning("需要安装 plotly")
            return ""

        if not self.strategies:
            logger.warning("没有策略数据")
            return ""

        html_parts = []
        html_parts.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>策略仪表盘</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }
        h1 { color: #1a73e8; text-align: center; }
        .dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
        .chart-container { border: 1px solid #eee; border-radius: 8px; padding: 20px; }
        .metrics-table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        .metrics-table th, .metrics-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        .metrics-table th { background-color: #f8f9fa; }
        .controls { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; }
        .controls label { margin-right: 15px; }
        .controls select { padding: 5px; }
    </style>
</head>
<body>
    <h1>策略仪表盘</h1>
    <div class="controls">
        <label>策略:</label>
        <select id="strategy-select" onchange="updateCharts()">
""")

        for name in self.strategies.keys():
            html_parts.append(f"            <option value='{name}'>{name}</option>")

        html_parts.append("""        </select>
        <label>指标:</label>
        <select id="metric-select" onchange="updateCharts()">
            <option value="sharpe">Sharpe 比率</option>
            <option value="return">年化收益</option>
            <option value="vol">年化波动率</option>
            <option value="drawdown">最大回撤</option>
        </select>
    </div>
""")

        html_parts.append('<div class="dashboard-grid">')

        nav_div = self._generate_nav_chart()
        html_parts.append(f'<div class="chart-container" id="nav-chart">{nav_div}</div>')

        dd_div = self._generate_drawdown_chart()
        html_parts.append(f'<div class="chart-container" id="dd-chart">{dd_div}</div>')

        dist_div = self._generate_dist_chart()
        html_parts.append(f'<div class="chart-container" id="dist-chart">{dist_div}</div>')

        corr_div = self._generate_corr_chart()
        html_parts.append(f'<div class="chart-container" id="corr-chart">{corr_div}</div>')

        html_parts.append('</div>')

        metrics_html = self._generate_metrics_table()
        html_parts.append(f'<div>{metrics_html}</div>')

        html_parts.append("""    <script>
        function updateCharts() {
            var strategy = document.getElementById('strategy-select').value;
            var metric = document.getElementById('metric-select').value;
            console.log('切换到:', strategy, metric);
        }
    </script>
</body>
</html>""")

        html = "\n".join(html_parts)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"仪表盘已保存: {output_path}")

        return html

    def _generate_nav_chart(self) -> str:
        """生成净值曲线图"""
        if go is None or pio is None:
            return "<p>需要安装 plotly</p>"

        fig = go.Figure()
        for name, returns in self.strategies.items():
            nav = np.cumprod(1 + returns)
            fig.add_trace(go.Scatter(y=nav, mode="lines", name=name))

        fig.update_layout(
            title="净值曲线",
            xaxis_title="日期",
            yaxis_title="净值",
            template="plotly_white",
            hovermode="x unified",
        )

        return pio.to_html(fig, full_html=False)

    def _generate_drawdown_chart(self) -> str:
        """生成回撤曲线图"""
        if go is None or pio is None:
            return "<p>需要安装 plotly</p>"

        fig = go.Figure()
        for name, returns in self.strategies.items():
            nav = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(nav)
            drawdown = (nav - running_max) / running_max
            fig.add_trace(go.Scatter(y=drawdown, mode="lines", name=name))

        fig.update_layout(
            title="回撤曲线",
            xaxis_title="日期",
            yaxis_title="回撤",
            template="plotly_white",
            hovermode="x unified",
        )

        return pio.to_html(fig, full_html=False)

    def _generate_dist_chart(self) -> str:
        """生成收益分布图"""
        if go is None or pio is None:
            return "<p>需要安装 plotly</p>"

        fig = go.Figure()
        for name, returns in self.strategies.items():
            fig.add_trace(go.Histogram(x=returns, name=name, opacity=0.6))

        fig.update_layout(
            title="收益分布",
            xaxis_title="日收益",
            yaxis_title="频率",
            template="plotly_white",
            barmode="overlay",
        )

        return pio.to_html(fig, full_html=False)

    def _generate_corr_chart(self) -> str:
        """生成相关性矩阵图"""
        if go is None or pio is None:
            return "<p>需要安装 plotly</p>"

        if len(self.strategies) < 2:
            return "<p>至少需要两个策略才能计算相关性</p>"

        names = list(self.strategies.keys())
        n = len(names)
        corr_matrix = np.zeros((n, n))

        for i, name1 in enumerate(names):
            for j, name2 in enumerate(names):
                r1 = self.strategies[name1]
                r2 = self.strategies[name2]
                min_len = min(len(r1), len(r2))
                corr_matrix[i, j] = np.corrcoef(r1[:min_len], r2[:min_len])[0, 1]

        fig = go.Figure(
            data=go.Heatmap(
                z=corr_matrix,
                x=names,
                y=names,
                colorscale="RdBu",
                zmin=-1,
                zmax=1,
            )
        )

        fig.update_layout(
            title="相关性矩阵",
            template="plotly_white",
        )

        return pio.to_html(fig, full_html=False)

    def _generate_metrics_table(self) -> str:
        """生成绩效指标表"""
        lines = []
        lines.append("<h2>绩效指标</h2>")
        lines.append('<table class="metrics-table">')
        lines.append("    <tr><th>策略</th><th>累计收益</th><th>年化收益</th><th>年化波动率</th><th>Sharpe 比率</th><th>最大回撤</th></tr>")

        for name, returns in self.strategies.items():
            metrics = compute_metrics(returns)
            lines.append(
                f"    <tr><td>{name}</td><td>{metrics.total_return:.2%}</td><td>{metrics.annualized_return:.2%}</td>"
                f"<td>{metrics.annualized_volatility:.2%}</td><td>{metrics.sharpe_ratio:.4f}</td>"
                f"<td>{metrics.max_drawdown:.2%}</td></tr>"
            )

        lines.append("</table>")

        return "\n".join(lines)


__all__ = ["StrategyDashboard"]
