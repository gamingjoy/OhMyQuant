"""调仓器单元测试

覆盖三个调仓器插件：
  - CostBenefitRebalancer（成本收益权衡）
  - SimpleRebalancer（简单调仓）
  - NoOpRebalancer（空操作）
  - create_rebalancer 工厂方法
"""
import pytest

from ohmyquant.execution.base import RebalanceResult
from ohmyquant.execution.cost_model import StockCostModel
from ohmyquant.execution.rebalancer import (
    BENEFIT_SCALE,
    CostBenefitRebalancer,
    NoOpRebalancer,
    SimpleRebalancer,
    create_rebalancer,
)


class TestCostBenefitRebalancer:
    """成本收益权衡调仓器测试"""

    def test_first_build(self):
        """首次建仓：空持仓 → 全部买入目标标的"""
        rebalancer = CostBenefitRebalancer()
        target = {"000001.SZ": 0.5, "000002.SZ": 0.5}
        result = rebalancer.decide({}, target)

        assert result.need_rebalance is True
        assert set(result.buys) == {"000001.SZ", "000002.SZ"}
        assert result.sells == []
        assert result.total_cost > 0  # 建仓有成本
        # final_weights 应等于 target（归一化后）
        assert pytest.approx(sum(result.final_weights.values()), rel=1e-9) == 1.0

    def test_sell_executed_when_benefit_exceeds_cost(self):
        """评分差足够大时执行卖出（net_benefit > 0）"""
        # cost_benefit_threshold=0, min_hold_days=0
        rebalancer = CostBenefitRebalancer({"cost_benefit_threshold": 0.0, "min_hold_days": 0})

        current = {"000001.SZ": 1.0}
        target = {"000002.SZ": 1.0}
        # 评分差 >> cost/scale → net_benefit > 0
        # sell_cost(1.0) = 0.00076; benefit = (best_buy - old) * 0.1
        # 需要 (0.9 - 0.1) * 0.1 = 0.08 > 0.00076
        scores = {"000001.SZ": 0.1, "000002.SZ": 0.9}

        result = rebalancer.decide(current, target, hold_days_map={"000001.SZ": 10}, scores=scores)

        assert result.need_rebalance is True
        assert "000001.SZ" in result.sells
        assert "000002.SZ" in result.buys
        # 卖出的标的不应在 final_weights 中
        assert "000001.SZ" not in result.final_weights
        assert "000002.SZ" in result.final_weights

    def test_sell_skipped_when_hold_days_insufficient(self):
        """持有天数不足最小持有期时强制跳过"""
        rebalancer = CostBenefitRebalancer({"min_hold_days": 30})

        current = {"000001.SZ": 1.0}
        target = {"000002.SZ": 1.0}
        scores = {"000001.SZ": 0.0, "000002.SZ": 1.0}

        result = rebalancer.decide(
            current, target, hold_days_map={"000001.SZ": 5}, scores=scores
        )

        # 持有 5 天 < 30 天，强制跳过
        assert len(result.skipped_sells) == 1
        assert result.skipped_sells[0]["code"] == "000001.SZ"
        # 跳过的标的保留旧权重
        assert "000001.SZ" in result.final_weights

    def test_sell_skipped_when_net_benefit_negative(self):
        """净收益为负时跳过卖出（评分差不足以覆盖成本）"""
        rebalancer = CostBenefitRebalancer({"cost_benefit_threshold": 0.0, "min_hold_days": 0})

        current = {"000001.SZ": 1.0}
        target = {"000002.SZ": 1.0}
        # 评分差很小: benefit = (0.1001 - 0.1) * 0.1 = 0.00001 < cost 0.00076
        scores = {"000001.SZ": 0.1, "000002.SZ": 0.1001}

        result = rebalancer.decide(
            current, target, hold_days_map={"000001.SZ": 10}, scores=scores
        )

        assert len(result.skipped_sells) == 1
        assert "000001.SZ" in result.final_weights  # 保留旧权重

    def test_final_weights_normalized(self):
        """final_weights 归一化（和为 1.0）"""
        rebalancer = CostBenefitRebalancer({"min_hold_days": 30})

        current = {"000001.SZ": 0.5, "000002.SZ": 0.5}
        target = {"000003.SZ": 0.5, "000004.SZ": 0.5}
        scores = {"000001.SZ": 0.0, "000002.SZ": 0.0, "000003.SZ": 1.0, "000004.SZ": 1.0}

        result = rebalancer.decide(
            current, target, hold_days_map={"000001.SZ": 1, "000002.SZ": 1}, scores=scores
        )

        # 两个卖出都被跳过（hold_days < 30），final = target + skipped
        total = sum(result.final_weights.values())
        assert pytest.approx(total, rel=1e-9) == 1.0

    def test_no_change_when_target_equals_current(self):
        """目标等于当前持仓时无调仓"""
        rebalancer = CostBenefitRebalancer()
        weights = {"000001.SZ": 0.5, "000002.SZ": 0.5}

        result = rebalancer.decide(weights, weights, hold_days_map={}, scores={})

        # sell_candidates 和 buy_candidates 都为空
        assert result.need_rebalance is False
        assert result.sells == []
        assert result.buys == []

    def test_empty_target_with_current(self):
        """当前有持仓但目标为空：所有持仓标记为卖出候选"""
        rebalancer = CostBenefitRebalancer({"min_hold_days": 0})
        current = {"000001.SZ": 1.0}
        scores = {"000001.SZ": 0.0}

        result = rebalancer.decide(current, {}, hold_days_map={"000001.SZ": 10}, scores=scores)

        # 无买入候选，best_buy_score=0，benefit=max(0-0,0)*0.1=0，net_benefit=0-cost<0
        # 所以卖出被跳过
        assert len(result.skipped_sells) == 1

    def test_cost_model_from_config(self):
        """配置中指定成本模型"""
        rebalancer = CostBenefitRebalancer({"cost_model": {"name": "stock_cn"}})
        assert isinstance(rebalancer.cost_model, StockCostModel)

    def test_cost_model_string_config(self):
        """成本模型配置为字符串"""
        rebalancer = CostBenefitRebalancer({"cost_model": "stock_cn"})
        assert isinstance(rebalancer.cost_model, StockCostModel)


class TestSimpleRebalancer:
    """简单调仓器测试"""

    def test_full_rebalance(self):
        """直接采用目标权重"""
        rebalancer = SimpleRebalancer()
        current = {"000001.SZ": 1.0}
        target = {"000002.SZ": 0.6, "000003.SZ": 0.4}

        result = rebalancer.decide(current, target)

        assert result.need_rebalance is True
        assert "000001.SZ" in result.sells
        assert set(result.buys) == {"000002.SZ", "000003.SZ"}
        assert result.final_weights == target
        assert result.total_cost > 0

    def test_first_build(self):
        """首次建仓"""
        rebalancer = SimpleRebalancer()
        target = {"000001.SZ": 0.5, "000002.SZ": 0.5}
        result = rebalancer.decide({}, target)

        assert result.need_rebalance is True
        assert set(result.buys) == {"000001.SZ", "000002.SZ"}

    def test_no_change(self):
        """目标等于当前时 need_rebalance=False"""
        rebalancer = SimpleRebalancer()
        weights = {"000001.SZ": 0.5, "000002.SZ": 0.5}

        result = rebalancer.decide(weights, weights)

        # sells=[], buys=[], current_weights 非空 → need_rebalance = False
        assert result.need_rebalance is False

    def test_empty_current_and_target(self):
        """空持仓和空目标"""
        rebalancer = SimpleRebalancer()
        result = rebalancer.decide({}, {})
        # sells=[], buys=[], not current_weights(空) → need_rebalance = True
        # 注：bool([]) or bool([]) = False, but not {} = True
        assert result.need_rebalance is True


class TestNoOpRebalancer:
    """空操作调仓器测试"""

    def test_no_rebalance(self):
        """不调仓，final_weights = current_weights"""
        rebalancer = NoOpRebalancer()
        current = {"000001.SZ": 0.6, "000002.SZ": 0.4}
        target = {"000003.SZ": 1.0}

        result = rebalancer.decide(current, target)

        assert result.need_rebalance is False
        assert result.final_weights == current
        assert result.sells == []
        assert result.buys == []

    def test_no_cost_model(self):
        """NoOpRebalancer 无成本模型"""
        rebalancer = NoOpRebalancer()
        assert rebalancer.cost_model is None

    def test_empty_current(self):
        """空持仓也不调仓"""
        rebalancer = NoOpRebalancer()
        result = rebalancer.decide({}, {"000001.SZ": 1.0})
        assert result.need_rebalance is False
        assert result.final_weights == {}


class TestCreateRebalancer:
    """工厂方法测试"""

    def test_create_cost_benefit(self):
        r = create_rebalancer({"method": "cost_benefit"})
        assert isinstance(r, CostBenefitRebalancer)

    def test_create_simple(self):
        r = create_rebalancer({"method": "simple"})
        assert isinstance(r, SimpleRebalancer)

    def test_create_none(self):
        r = create_rebalancer({"method": "none"})
        assert isinstance(r, NoOpRebalancer)

    def test_create_default(self):
        """未指定 method 默认 cost_benefit"""
        r = create_rebalancer({})
        assert isinstance(r, CostBenefitRebalancer)

    def test_create_empty_config(self):
        """空配置默认 cost_benefit"""
        r = create_rebalancer(None)
        assert isinstance(r, CostBenefitRebalancer)


class TestRebalanceResult:
    """RebalanceResult 数据类测试"""

    def test_net_benefit(self):
        """net_benefit = total_benefit - total_cost"""
        r = RebalanceResult(total_cost=0.001, total_benefit=0.005)
        assert r.net_benefit == pytest.approx(0.004)

    def test_default_values(self):
        """默认值"""
        r = RebalanceResult()
        assert r.need_rebalance is False
        assert r.sells == []
        assert r.buys == []
        assert r.skipped_sells == []
        assert r.total_cost == 0.0
        assert r.total_benefit == 0.0
        assert r.final_weights == {}
