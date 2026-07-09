"""因子测试工作流

完整的因子测试流程：加载 → 计算 → IC分析 → 分位数 → 衰减 → 报告
"""
from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from ..core.logging import get_logger
from ..data.base import DataCatalog
from .analysis import FactorAnalyzer, FactorStats, QuantileAnalysis, compute_all_returns
from .base import FactorRegistry

logger = get_logger(__name__)


@dataclass
class FactorTestResult:
    """因子测试结果"""

    factor_name: str
    stats: FactorStats = field(default_factory=FactorStats)
    quantile: QuantileAnalysis | None = None
    ic_decay: dict[int, float] = field(default_factory=dict)
    ic_series: pl.DataFrame | None = None

    def summary(self) -> str:
        """生成摘要文本"""
        lines = [
            f"因子: {self.factor_name}",
            f"  IC均值: {self.stats.ic_mean:.4f}",
            f"  IC标准差: {self.stats.ic_std:.4f}",
            f"  ICIR: {self.stats.icir:.4f}",
            f"  IC胜率: {self.stats.ic_positive_ratio:.2%}",
            f"  IC绝对值均值: {self.stats.ic_abs_mean:.4f}",
            f"  样本数: {self.stats.n_obs}",
        ]
        if self.quantile:
            lines.append(f"  分位数多空收益: {self.quantile.long_short_return:.4%}")
            for g, ret in self.quantile.group_returns.items():
                lines.append(f"    第{g}组: {ret:.4%}")
        if self.ic_decay:
            lines.append("  IC衰减:")
            for h, ic in self.ic_decay.items():
                lines.append(f"    {h}日: {ic:.4f}")
        return "\n".join(lines)


class FactorTester:
    """因子测试器

    用法:
        from ohmyquant.data import DuckDBSource, DataCatalog
        from ohmyquant.factors.testing import FactorTester

        catalog = DataCatalog(DuckDBSource())
        tester = FactorTester(catalog)
        result = tester.test_factor("mom_1m", codes=["000001.SZ", ...],
                                     start_date="2020-01-01", end_date="2024-12-31")
        print(result.summary())
    """

    def __init__(self, data_catalog: DataCatalog):
        self.catalog = data_catalog
        self.analyzer = FactorAnalyzer()

    def test_factor(
        self,
        factor_name: str,
        codes: list[str],
        start_date: str,
        end_date: str,
        forward_horizon: int = 20,
        n_groups: int = 5,
    ) -> FactorTestResult:
        """测试单个因子

        Args:
            factor_name: 因子注册名
            codes: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            forward_horizon: 前向收益持有期
            n_groups: 分位数组数

        Returns:
            FactorTestResult
        """
        logger.info(f"测试因子: {factor_name} ({len(codes)} 只股票)")

        # 1. 加载数据
        ohlcv = self.catalog.get_ohlcv(codes, start_date, end_date)

        # 2. 计算因子
        factor = FactorRegistry.create(factor_name)
        factor_values = factor.compute(ohlcv)

        # 3. 计算前向收益
        forward_returns = compute_all_returns(ohlcv["close"], forward_horizon)

        # 4. IC分析
        ic_series = self.analyzer.compute_ic(factor_values, forward_returns)
        stats = self.analyzer.compute_icir(ic_series)
        stats.factor_name = factor_name

        # 5. 分位数收益
        quantile = self.analyzer.compute_quantile_returns(
            factor_values, forward_returns, n_groups
        )
        quantile.factor_name = factor_name

        # 6. IC衰减
        ic_decay = self.analyzer.compute_ic_decay(
            factor_values, ohlcv["close"], horizons=[5, 10, 20, 40, 60]
        )

        result = FactorTestResult(
            factor_name=factor_name,
            stats=stats,
            quantile=quantile,
            ic_decay=ic_decay,
            ic_series=ic_series,
        )

        logger.info(
            f"因子 {factor_name} 测试完成: IC={stats.ic_mean:.4f}, ICIR={stats.icir:.4f}"
        )
        return result

    def test_factor_group(
        self,
        factor_names: list[str],
        codes: list[str],
        start_date: str,
        end_date: str,
        forward_horizon: int = 20,
    ) -> pl.DataFrame:
        """批量测试因子组，返回汇总表

        Returns:
            DataFrame: factor, ic_mean, ic_std, icir, ic_positive_ratio, ic_abs_mean
        """
        results = []
        for name in factor_names:
            try:
                r = self.test_factor(name, codes, start_date, end_date, forward_horizon)
                results.append(
                    {
                        "factor": name,
                        "ic_mean": r.stats.ic_mean,
                        "ic_std": r.stats.ic_std,
                        "icir": r.stats.icir,
                        "ic_positive_ratio": r.stats.ic_positive_ratio,
                        "ic_abs_mean": r.stats.ic_abs_mean,
                        "long_short_return": (
                            r.quantile.long_short_return if r.quantile else None
                        ),
                    }
                )
            except Exception as e:
                logger.warning(f"测试因子 {name} 失败: {e}")
                results.append(
                    {
                        "factor": name,
                        "ic_mean": None,
                        "ic_std": None,
                        "icir": None,
                        "ic_positive_ratio": None,
                        "ic_abs_mean": None,
                        "long_short_return": None,
                    }
                )

        df = pl.DataFrame(results)
        if not df.is_empty():
            df = df.sort("icir", descending=True)
        return df


__all__ = ["FactorTester", "FactorTestResult"]
