"""统计显著性测试

提供策略收益的统计显著性检验：
  - t检验：检验超额收益是否显著不为零
  - Bootstrap：生成收益分布的置信区间
  - Deflated Sharpe Ratio：多重检验校正后的 Sharpe 比率

参考：
  - Lo, A. W. (2004). The Statistics of Sharpe Ratios.
  - Bailey, D. H., & López de Prado, M. (2012). The Sharpe Ratio Efficient Frontier.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from ..core.logging import get_logger

logger = get_logger(__name__)

TRADING_DAYS = 242


@dataclass
class SignificanceResult:
    """显著性测试结果"""

    t_statistic: float = 0.0
    p_value: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    sharpe_ratio: float = 0.0
    dsr: float = 0.0
    bootstrap_sharpe_ci: tuple[float, float] = (0.0, 0.0)
    num_trials: int = 1


class SignificanceTester:
    """显著性测试器"""

    def __init__(self, returns: np.ndarray):
        """初始化

        Args:
            returns: 每日收益序列
        """
        self.returns = returns

    def t_test(self, benchmark_returns: np.ndarray | None = None) -> SignificanceResult:
        """t检验超额收益

        Args:
            benchmark_returns: 基准收益序列（可选）

        Returns:
            SignificanceResult
        """
        if benchmark_returns is not None:
            excess = self.returns - benchmark_returns[: len(self.returns)]
        else:
            excess = self.returns

        if len(excess) < 2:
            return SignificanceResult()

        t_stat, p_value = stats.ttest_1samp(excess, 0)

        sharpe = self._compute_sharpe(excess)

        return SignificanceResult(
            t_statistic=t_stat,
            p_value=p_value,
            sharpe_ratio=sharpe,
        )

    def bootstrap_sharpe(
        self, n_samples: int = 1000, confidence: float = 0.95
    ) -> SignificanceResult:
        """Bootstrap Sharpe 置信区间"""
        if len(self.returns) < 10:
            return SignificanceResult()

        sharpe_values = []
        for _ in range(n_samples):
            sample = np.random.choice(self.returns, size=len(self.returns), replace=True)
            sharpe_values.append(self._compute_sharpe(sample))

        sharpe_values = np.array(sharpe_values)
        lower = np.percentile(sharpe_values, (1 - confidence) * 50)
        upper = np.percentile(sharpe_values, confidence * 100 - (1 - confidence) * 50)

        return SignificanceResult(
            sharpe_ratio=self._compute_sharpe(self.returns),
            bootstrap_sharpe_ci=(lower, upper),
            num_trials=n_samples,
        )

    def deflated_sharpe_ratio(
        self, num_trials: int = 100, n_samples: int = 1000
    ) -> SignificanceResult:
        """计算 Deflated Sharpe Ratio（DSR）

        Args:
            num_trials: 策略数量（用于多重检验校正）
            n_samples: Bootstrap 样本数

        Returns:
            SignificanceResult
        """
        if len(self.returns) < 10:
            return SignificanceResult()

        sharpe_observed = self._compute_sharpe(self.returns)

        max_sharpe_values = []
        for _ in range(n_samples):
            max_sharpe = -np.inf
            for _ in range(num_trials):
                sample = np.random.choice(self.returns, size=len(self.returns), replace=True)
                sharpe = self._compute_sharpe(sample)
                if sharpe > max_sharpe:
                    max_sharpe = sharpe
            max_sharpe_values.append(max_sharpe)

        dsr = np.mean(np.array(max_sharpe_values) >= sharpe_observed)

        return SignificanceResult(
            sharpe_ratio=sharpe_observed,
            dsr=dsr,
            num_trials=num_trials,
        )

    def _compute_sharpe(self, returns: np.ndarray) -> float:
        """计算 Sharpe 比率"""
        if len(returns) < 2:
            return 0.0
        vol = np.std(returns, ddof=1)
        if vol == 0:
            return 0.0
        return np.mean(returns) / vol * np.sqrt(TRADING_DAYS)

    def run_all(
        self, benchmark_returns: np.ndarray | None = None, num_trials: int = 100
    ) -> SignificanceResult:
        """运行所有显著性测试"""
        t_result = self.t_test(benchmark_returns)
        bootstrap_result = self.bootstrap_sharpe()
        dsr_result = self.deflated_sharpe_ratio(num_trials=num_trials)

        return SignificanceResult(
            t_statistic=t_result.t_statistic,
            p_value=t_result.p_value,
            sharpe_ratio=t_result.sharpe_ratio,
            bootstrap_sharpe_ci=bootstrap_result.bootstrap_sharpe_ci,
            dsr=dsr_result.dsr,
            num_trials=num_trials,
        )

    def print_results(self) -> None:
        """打印显著性测试结果"""
        result = self.run_all()
        print("=" * 60)
        print("统计显著性测试")
        print("=" * 60)
        print(f"t统计量:           {result.t_statistic:>12.4f}")
        print(f"p值:               {result.p_value:>12.4f}")
        print(f"Sharpe 比率:       {result.sharpe_ratio:>12.4f}")
        print(f"Bootstrap 95% CI:  ({result.bootstrap_sharpe_ci[0]:.4f}, {result.bootstrap_sharpe_ci[1]:.4f})")
        print(f"DSR:               {result.dsr:>12.4f}")
        print("=" * 60)


__all__ = ["SignificanceResult", "SignificanceTester"]
