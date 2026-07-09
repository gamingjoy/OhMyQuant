"""分析模块测试

测试分析功能：
  - 绩效指标计算
  - 多策略对比
  - 统计显著性检验
"""
import numpy as np
import pytest

from ohmyquant.analysis.metrics import (
    PerformanceMetrics,
    compute_metrics,
    compute_total_return,
    compute_annualized_return,
    compute_sharpe_ratio,
    compute_max_drawdown,
)
from ohmyquant.analysis.compare import StrategyComparator
from ohmyquant.analysis.significance import SignificanceTester


class TestMetrics:
    """绩效指标测试"""

    def test_compute_total_return(self):
        """测试累计收益计算"""
        returns = np.array([0.01, 0.02, -0.01, 0.03])
        total_return = compute_total_return(returns)
        assert total_return > 0
        assert np.isclose(total_return, 1.01 * 1.02 * 0.99 * 1.03 - 1, rtol=1e-4)

    def test_compute_annualized_return(self):
        """测试年化收益计算"""
        returns = np.array([0.01] * 242)
        annual_return = compute_annualized_return(returns)
        assert annual_return > 0

    def test_compute_sharpe_ratio(self):
        """测试 Sharpe 比率计算"""
        returns = np.array([0.01, 0.02, 0.005, 0.015, 0.008])
        sharpe = compute_sharpe_ratio(returns)
        assert isinstance(sharpe, float)

    def test_compute_max_drawdown(self):
        """测试最大回撤计算"""
        returns = np.array([0.1, 0.1, -0.15, -0.1, 0.05])
        max_dd, _ = compute_max_drawdown(returns)
        assert max_dd < 0

    def test_compute_metrics(self):
        """测试综合指标计算"""
        returns = np.array([0.01, 0.02, -0.01, 0.03, 0.005])
        metrics = compute_metrics(returns)
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_return > 0
        assert metrics.sharpe_ratio is not None
        assert metrics.max_drawdown <= 0
        assert metrics.n_days == len(returns)


class TestStrategyComparator:
    """策略对比器测试"""

    def test_init(self):
        """测试初始化"""
        strategies = {
            "strategy_a": np.array([0.01, 0.02, -0.01]),
            "strategy_b": np.array([0.008, 0.015, 0.005]),
        }
        comparator = StrategyComparator(strategies)
        assert comparator.strategies == strategies

    def test_compute_correlation_matrix(self):
        """测试相关性矩阵计算"""
        strategies = {
            "strategy_a": np.array([0.01, 0.02, -0.01, 0.03]),
            "strategy_b": np.array([0.008, 0.015, -0.005, 0.02]),
            "strategy_c": np.array([0.005, 0.01, 0.008, -0.01]),
        }
        comparator = StrategyComparator(strategies)
        corr_matrix = comparator.compute_correlation_matrix()
        
        assert corr_matrix is not None
        assert "strategy" in corr_matrix.columns

    def test_get_comparison_table(self):
        """测试对比表生成"""
        strategies = {
            "strategy_a": np.array([0.01, 0.02, -0.01]),
            "strategy_b": np.array([0.008, 0.015, 0.005]),
        }
        comparator = StrategyComparator(strategies)
        table = comparator.get_comparison_table()
        
        assert table is not None
        assert len(table) == 2


class TestSignificanceTester:
    """显著性测试器测试"""

    def test_t_test(self):
        """测试 t 检验"""
        returns = np.array([0.01, 0.02, 0.015, 0.008, 0.025])
        tester = SignificanceTester(returns)
        result = tester.t_test()
        
        assert isinstance(result.t_statistic, float)
        assert isinstance(result.p_value, float)

    def test_bootstrap_sharpe(self):
        """测试 Bootstrap Sharpe"""
        returns = np.array([0.01, 0.02, -0.01, 0.03, 0.005] * 10)
        tester = SignificanceTester(returns)
        result = tester.bootstrap_sharpe(n_samples=100)
        
        assert result.bootstrap_sharpe_ci is not None
        assert len(result.bootstrap_sharpe_ci) == 2

    def test_deflated_sharpe_ratio(self):
        """测试 Deflated Sharpe Ratio"""
        returns = np.array([0.01, 0.02, -0.01, 0.03, 0.005] * 10)
        tester = SignificanceTester(returns)
        result = tester.deflated_sharpe_ratio(num_trials=10, n_samples=50)
        
        assert isinstance(result.dsr, float)
        assert 0 <= result.dsr <= 1
