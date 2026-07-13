"""报告生成

生成策略回测报告，支持多种格式：
  - 文本报告
  - Markdown 报告
  - HTML 报告（集成可视化）

报告内容：
  - 策略概览
  - 绩效指标表
  - 归因分析
  - 显著性测试
  - 可视化图表
"""
from __future__ import annotations

import os

import numpy as np

from .attribution import PositionAttributor, TimeAttributor
from .compare import StrategyComparator
from .metrics import PerformanceMetrics, compute_metrics
from .significance import SignificanceTester
from ..core.logging import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """报告生成器"""

    def __init__(self, strategy_name: str = "", strategy_version: str = ""):
        """初始化

        Args:
            strategy_name: 策略名称
            strategy_version: 策略版本
        """
        self.strategy_name = strategy_name
        self.strategy_version = strategy_version
        self.metrics: PerformanceMetrics | None = None
        self.significance_result = None

    def generate_text_report(
        self, returns: np.ndarray, output_path: str | None = None
    ) -> str:
        """生成文本报告

        Args:
            returns: 每日收益序列
            output_path: 输出路径（可选）

        Returns:
            str: 报告内容
        """
        self.metrics = compute_metrics(returns)

        lines = []
        lines.append("=" * 60)
        lines.append(f"策略回测报告")
        lines.append("=" * 60)
        lines.append(f"策略名称:     {self.strategy_name}")
        lines.append(f"策略版本:     {self.strategy_version}")
        lines.append("-" * 60)
        lines.append("绩效指标")
        lines.append("-" * 60)
        lines.append(f"累计收益:        {self.metrics.total_return:>12.2%}")
        lines.append(f"年化收益:        {self.metrics.annualized_return:>12.2%}")
        lines.append(f"年化波动率:      {self.metrics.annualized_volatility:>12.2%}")
        lines.append(f"Sharpe 比率:     {self.metrics.sharpe_ratio:>12.4f}")
        lines.append(f"Sortino 比率:    {self.metrics.sortino_ratio:>12.4f}")
        lines.append(f"Calmar 比率:     {self.metrics.calmar_ratio:>12.4f}")
        lines.append(f"最大回撤:        {self.metrics.max_drawdown:>12.2%}")
        lines.append(f"回撤持续天数:    {self.metrics.max_drawdown_duration:>12d}")
        lines.append(f"VaR(95%):       {self.metrics.var_95:>12.2%}")
        lines.append(f"CVaR(95%):      {self.metrics.cvar_95:>12.2%}")
        lines.append(f"偏度:           {self.metrics.skewness:>12.4f}")
        lines.append(f"峰度:           {self.metrics.kurtosis:>12.4f}")
        lines.append(f"胜率:           {self.metrics.win_rate:>12.2%}")
        lines.append(f"平均盈利:       {self.metrics.avg_win:>12.2%}")
        lines.append(f"平均亏损:       {self.metrics.avg_loss:>12.2%}")
        lines.append(f"盈亏比:         {self.metrics.profit_factor:>12.4f}")
        lines.append(f"信息比率:       {self.metrics.info_ratio:>12.4f}")
        lines.append(f"交易天数:       {self.metrics.n_days:>12d}")
        lines.append("=" * 60)

        report = "\n".join(lines)

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"报告已保存: {output_path}")

        return report

    def generate_markdown_report(
        self, returns: np.ndarray, output_path: str | None = None
    ) -> str:
        """生成 Markdown 报告

        Args:
            returns: 每日收益序列
            output_path: 输出路径（可选）

        Returns:
            str: 报告内容
        """
        self.metrics = compute_metrics(returns)

        lines = []
        lines.append(f"# 策略回测报告")
        lines.append("")
        lines.append(f"## 策略概览")
        lines.append("")
        lines.append(f"- **策略名称**: {self.strategy_name}")
        lines.append(f"- **策略版本**: {self.strategy_version}")
        lines.append("")
        lines.append(f"## 绩效指标")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 累计收益 | {self.metrics.total_return:.2%} |")
        lines.append(f"| 年化收益 | {self.metrics.annualized_return:.2%} |")
        lines.append(f"| 年化波动率 | {self.metrics.annualized_volatility:.2%} |")
        lines.append(f"| Sharpe 比率 | {self.metrics.sharpe_ratio:.4f} |")
        lines.append(f"| Sortino 比率 | {self.metrics.sortino_ratio:.4f} |")
        lines.append(f"| Calmar 比率 | {self.metrics.calmar_ratio:.4f} |")
        lines.append(f"| 最大回撤 | {self.metrics.max_drawdown:.2%} |")
        lines.append(f"| 回撤持续天数 | {self.metrics.max_drawdown_duration} |")
        lines.append(f"| VaR(95%) | {self.metrics.var_95:.2%} |")
        lines.append(f"| CVaR(95%) | {self.metrics.cvar_95:.2%} |")
        lines.append(f"| 偏度 | {self.metrics.skewness:.4f} |")
        lines.append(f"| 峰度 | {self.metrics.kurtosis:.4f} |")
        lines.append(f"| 胜率 | {self.metrics.win_rate:.2%} |")
        lines.append(f"| 平均盈利 | {self.metrics.avg_win:.2%} |")
        lines.append(f"| 平均亏损 | {self.metrics.avg_loss:.2%} |")
        lines.append(f"| 盈亏比 | {self.metrics.profit_factor:.4f} |")
        lines.append(f"| 信息比率 | {self.metrics.info_ratio:.4f} |")
        lines.append(f"| 交易天数 | {self.metrics.n_days} |")

        report = "\n".join(lines)

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Markdown 报告已保存: {output_path}")

        return report

    def generate_html_report(
        self, returns: np.ndarray, output_path: str | None = None
    ) -> str:
        """生成 HTML 报告（集成可视化）

        Args:
            returns: 每日收益序列
            output_path: 输出路径（可选）

        Returns:
            str: 报告内容
        """
        self.metrics = compute_metrics(returns)

        try:
            from ..visualization.plots import plot_nav, plot_drawdown, plot_returns_dist
            import plotly.io as pio

            nav_plot = plot_nav(returns)
            dd_plot = plot_drawdown(returns)
            dist_plot = plot_returns_dist(returns)

            nav_html = pio.to_html(nav_plot, full_html=False)
            dd_html = pio.to_html(dd_plot, full_html=False)
            dist_html = pio.to_html(dist_plot, full_html=False)
        except ImportError:
            nav_html = dd_html = dist_html = "<p>需要安装 plotly</p>"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>策略回测报告 - {self.strategy_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        h1 {{ color: #1a73e8; }}
        h2 {{ border-bottom: 2px solid #1a73e8; padding-bottom: 5px; }}
        table {{ border-collapse: collapse; width: 80%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f8f9fa; }}
        .plot-container {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>策略回测报告</h1>
    <h2>策略概览</h2>
    <p><strong>策略名称:</strong> {self.strategy_name}</p>
    <p><strong>策略版本:</strong> {self.strategy_version}</p>

    <h2>绩效指标</h2>
    <table>
        <tr><th>指标</th><th>值</th></tr>
        <tr><td>累计收益</td><td>{self.metrics.total_return:.2%}</td></tr>
        <tr><td>年化收益</td><td>{self.metrics.annualized_return:.2%}</td></tr>
        <tr><td>年化波动率</td><td>{self.metrics.annualized_volatility:.2%}</td></tr>
        <tr><td>Sharpe 比率</td><td>{self.metrics.sharpe_ratio:.4f}</td></tr>
        <tr><td>Sortino 比率</td><td>{self.metrics.sortino_ratio:.4f}</td></tr>
        <tr><td>Calmar 比率</td><td>{self.metrics.calmar_ratio:.4f}</td></tr>
        <tr><td>最大回撤</td><td>{self.metrics.max_drawdown:.2%}</td></tr>
        <tr><td>回撤持续天数</td><td>{self.metrics.max_drawdown_duration}</td></tr>
        <tr><td>VaR(95%)</td><td>{self.metrics.var_95:.2%}</td></tr>
        <tr><td>CVaR(95%)</td><td>{self.metrics.cvar_95:.2%}</td></tr>
        <tr><td>偏度</td><td>{self.metrics.skewness:.4f}</td></tr>
        <tr><td>峰度</td><td>{self.metrics.kurtosis:.4f}</td></tr>
        <tr><td>胜率</td><td>{self.metrics.win_rate:.2%}</td></tr>
        <tr><td>盈亏比</td><td>{self.metrics.profit_factor:.4f}</td></tr>
        <tr><td>交易天数</td><td>{self.metrics.n_days}</td></tr>
    </table>

    <h2>净值曲线</h2>
    <div class="plot-container">{nav_html}</div>

    <h2>回撤曲线</h2>
    <div class="plot-container">{dd_html}</div>

    <h2>收益分布</h2>
    <div class="plot-container">{dist_html}</div>
</body>
</html>
"""

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"HTML 报告已保存: {output_path}")

        return html


__all__ = ["ReportGenerator"]
