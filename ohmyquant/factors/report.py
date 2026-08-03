"""因子自动报告

一键生成因子的完整分析报告，包括:
  - IC/ICIR 统计
  - 分位数组合收益
  - IC 衰减分析
  - 因子元数据

输出格式: Markdown
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from ..core.logging import get_logger
from .analysis import FactorAnalyzer, FactorStats, QuantileAnalysis
from .base import FactorRegistry

logger = get_logger(__name__)


class FactorReportGenerator:
    """因子报告生成器

    用法:
        gen = FactorReportGenerator()
        report = gen.generate(
            factor_name="mom_1m",
            factor_values=fv_df,
            forward_returns=fr_df,
            close=close_df,
        )
        gen.save(report, "reports/mom_1m_report.md")
    """

    def __init__(self, n_groups: int = 5, decay_horizons: list[int] | None = None):
        """初始化

        Args:
            n_groups: 分位数分组数
            decay_horizons: IC 衰减分析的持有期列表
        """
        self.n_groups = n_groups
        self.decay_horizons = decay_horizons or [5, 10, 20, 40, 60]

    def generate(
        self,
        factor_name: str,
        factor_values: pl.DataFrame,
        forward_returns: pl.DataFrame,
        close: pl.DataFrame | None = None,
    ) -> str:
        """生成完整因子报告

        Args:
            factor_name: 因子名
            factor_values: date × code 因子值宽表
            forward_returns: date × code 前向收益宽表
            close: date × code 收盘价宽表（用于 IC 衰减分析，可选）

        Returns:
            Markdown 格式的报告字符串
        """
        sections: list[str] = []

        # 1. 因子元数据
        metadata = self._get_metadata(factor_name)
        sections.append(self._format_metadata(metadata))

        # 2. IC/ICIR 分析
        ic_df = FactorAnalyzer.compute_ic(factor_values, forward_returns)
        stats = FactorAnalyzer.compute_icir(ic_df)
        sections.append(self._format_ic_stats(stats))

        # 3. 分位数收益
        quantile = FactorAnalyzer.compute_quantile_returns(
            factor_values, forward_returns, n_groups=self.n_groups
        )
        sections.append(self._format_quantile(quantile))

        # 4. IC 衰减（可选）
        if close is not None:
            decay = FactorAnalyzer.compute_ic_decay(
                factor_values, close, horizons=self.decay_horizons
            )
            sections.append(self._format_decay(decay))

        return "\n\n".join(sections) + "\n"

    def save(self, report: str, output_path: str | Path) -> None:
        """保存报告到文件"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        logger.info(f"因子报告已保存: {path}")

    def _get_metadata(self, factor_name: str) -> dict:
        """获取因子元数据"""
        try:
            return FactorRegistry.get_info(factor_name)
        except Exception:
            return {"name": factor_name, "category": "unknown"}

    @staticmethod
    def _format_metadata(meta: dict) -> str:
        """格式化元数据部分"""
        lines = [
            f"# 因子报告: {meta.get('name', 'unknown')}",
            "",
            "## 元数据",
            "",
            f"| 属性 | 值 |",
            f"|------|------|",
            f"| 名称 | {meta.get('name', '')} |",
            f"| 类别 | {meta.get('category', '')} |",
            f"| 描述 | {meta.get('description', '')} |",
            f"| 方向 | {'正向(值大→收益高)' if meta.get('direction', 1) > 0 else '反向(值小→收益高)'} |",
            f"| 所需数据 | {', '.join(meta.get('required_fields', []))} |",
            f"| 版本 | {meta.get('version', 'v1')} |",
        ]
        params = meta.get("params", {})
        if params:
            lines.append(f"| 参数 | {params} |")
        deps = meta.get("depends_on", [])
        if deps:
            lines.append(f"| 依赖因子 | {', '.join(deps)} |")
        return "\n".join(lines)

    @staticmethod
    def _format_ic_stats(stats: FactorStats) -> str:
        """格式化 IC/ICIR 部分"""
        return (
            "## IC / ICIR 分析\n\n"
            "| 指标 | 值 |\n"
            "|------|------|\n"
            f"| IC 均值 | {stats.ic_mean:.4f} |\n"
            f"| IC 标准差 | {stats.ic_std:.4f} |\n"
            f"| ICIR | {stats.icir:.4f} |\n"
            f"| IC 正比率 | {stats.ic_positive_ratio:.2%} |\n"
            f"| IC 绝对值均值 | {stats.ic_abs_mean:.4f} |\n"
            f"| 观测数 | {stats.n_obs} |"
        )

    def _format_quantile(self, quantile: QuantileAnalysis) -> str:
        """格式化分位数收益部分"""
        lines = [
            "## 分位数组合收益",
            "",
            "| 分组 | 平均收益 |",
            "|------|----------|",
        ]
        for g in sorted(quantile.group_returns.keys()):
            ret = quantile.group_returns[g]
            lines.append(f"| Q{g} | {ret:.4%} |")
        lines.append(f"| 多空收益 (Q1-Q{quantile.n_groups}) | {quantile.long_short_return:.4%} |")
        return "\n".join(lines)

    def _format_decay(self, decay: dict[int, float]) -> str:
        """格式化 IC 衰减部分"""
        lines = [
            "## IC 衰减分析",
            "",
            "| 持有期(天) | IC 均值 |",
            "|------------|---------|",
        ]
        for h in sorted(decay.keys()):
            lines.append(f"| {h} | {decay[h]:.4f} |")
        return "\n".join(lines)


__all__ = ["FactorReportGenerator"]
