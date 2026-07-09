"""调仓器实现

三个调仓器插件，参考 ETF_portfolio 的 Rebalancer，泛化到 WeightMap 权重格式。

配置中通过 rebalance.method 切换:
  method: cost_benefit → CostBenefitRebalancer（成本收益权衡，仅净收益为正时调仓）
  method: simple       → SimpleRebalancer（直接采用目标权重，仅计算成本）
  method: none         → NoOpRebalancer（不调仓）
"""
from __future__ import annotations

from ..core.logging import get_logger
from ..core.plugin_system import register_rebalancer
from ..core.types import WeightMap
from .base import BaseRebalancer, RebalanceResult
from .cost_model import BaseCostModel, create_cost_model

logger = get_logger(__name__)

# 收益提升系数：评分差 × 此系数 = 预期收益提升
BENEFIT_SCALE = 0.1


@register_rebalancer("cost_benefit")
class CostBenefitRebalancer(BaseRebalancer):
    """成本收益权衡调仓器

    评估每个卖出候选的成本与预期收益提升，仅当净收益 > threshold 时执行调仓。
    跳过成本过高的调仓，跳过的卖出标的保留在 final_weights 中。

    参考 ETF_portfolio 的 Rebalancer._evaluate_sells + _apply_decision。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = config or {}

        # 创建成本模型
        cost_model_cfg = cfg.get("cost_model", {"name": "stock_cn"})
        if isinstance(cost_model_cfg, str):
            cost_model_cfg = {"name": cost_model_cfg}
        self.cost_model: BaseCostModel = create_cost_model(cost_model_cfg)

    def decide(
        self,
        current_weights: WeightMap,
        target_weights: WeightMap,
        hold_days_map: dict[str, int] | None = None,
        scores: dict[str, float] | None = None,
    ) -> RebalanceResult:
        """调仓决策"""
        result = RebalanceResult()
        hold_days_map = hold_days_map or {}
        scores = scores or {}

        # 首次建仓
        if not current_weights:
            result.need_rebalance = True
            result.buys = list(target_weights.keys())
            result.total_cost = self.cost_model.estimate({}, target_weights)
            result.final_weights = dict(target_weights)
            logger.debug(f"首次建仓: 买入 {len(result.buys)} 只标的")
            return result

        old_codes = set(current_weights)
        new_codes = set(target_weights)
        sell_candidates = old_codes - new_codes
        buy_candidates = new_codes - old_codes

        # 评估每个卖出候选
        sell_eval = self._evaluate_sells(
            sell_candidates, buy_candidates, hold_days_map, scores
        )

        # 应用决策
        self._apply_decision(
            sell_eval, buy_candidates, scores, current_weights, target_weights, result
        )

        return result

    def _evaluate_sells(
        self,
        sell_candidates: set,
        buy_candidates: set,
        hold_days_map: dict[str, int],
        scores: dict[str, float],
    ) -> list[dict]:
        """评估每个卖出候选的成本收益

        Returns:
            按 net_benefit 降序排列的评估列表
        """
        sell_eval: list[dict] = []

        # 找最佳买入候选（评分最高）
        best_buy_code = None
        best_buy_score = 0.0
        if buy_candidates:
            best_buy_code = max(
                buy_candidates, key=lambda c: scores.get(c, 0.0)
            )
            best_buy_score = scores.get(best_buy_code, 0.0)

        for code in sell_candidates:
            hold_days = hold_days_map.get(code, 0)
            old_score = scores.get(code, 0.0)

            # 持有天数不足，强制跳过（成本无穷大）
            if hold_days < self.min_hold_days:
                cost = float("inf")
                benefit = 0.0
                net_benefit = float("-inf")
            else:
                # 卖出成本（按权重 1.0 估算，实际权重在 _apply_decision 中处理）
                cost = self.cost_model.sell_cost(1.0, hold_days, code)
                # 预期收益提升 = (最佳买入评分 - 当前评分) × 系数
                benefit = max(best_buy_score - old_score, 0.0) * BENEFIT_SCALE
                net_benefit = benefit - cost

            sell_eval.append(
                {
                    "sell_code": code,
                    "best_buy_code": best_buy_code,
                    "hold_days": hold_days,
                    "cost": cost,
                    "benefit": benefit,
                    "net_benefit": net_benefit,
                }
            )

        # 按 net_benefit 降序排列
        sell_eval.sort(key=lambda x: x["net_benefit"], reverse=True)
        return sell_eval

    def _apply_decision(
        self,
        sell_eval: list[dict],
        buy_candidates: set,
        scores: dict[str, float],
        current_weights: WeightMap,
        target_weights: WeightMap,
        result: RebalanceResult,
    ) -> None:
        """应用调仓决策

        净收益 > threshold 的执行卖出，配对最佳买入。
        跳过的卖出标的保留在 final_weights 中（从 current_weights 恢复权重）。
        """
        actual_sells: set = set()
        actual_buys: set = set()
        used_buys: set = set()
        skipped_codes: set = set()

        for ev in sell_eval:
            if ev["net_benefit"] > self.cost_benefit_threshold:
                actual_sells.add(ev["sell_code"])
                if ev["best_buy_code"] and ev["best_buy_code"] not in used_buys:
                    actual_buys.add(ev["best_buy_code"])
                    used_buys.add(ev["best_buy_code"])
                result.total_cost += ev["cost"]
                result.total_benefit += ev["benefit"]
            else:
                # 跳过的卖出标的
                reason = self._format_skip_reason(ev, scores)
                result.skipped_sells.append(
                    {
                        "code": ev["sell_code"],
                        "hold_days": ev["hold_days"],
                        "cost": ev["cost"],
                        "benefit": ev["benefit"],
                        "reason": reason,
                    }
                )
                skipped_codes.add(ev["sell_code"])

        # 未配对的买入候选也加入
        for code in buy_candidates:
            if code not in used_buys:
                actual_buys.add(code)
                used_buys.add(code)

        # 构建 final_weights
        # 1. 目标权重（买入新标的 + 调整持有标的）
        final_weights: dict[str, float] = dict(target_weights)

        # 2. 跳过的卖出标的保留旧权重
        for code in skipped_codes:
            if code in current_weights:
                final_weights[code] = current_weights[code]

        # 3. 移除实际卖出的标的
        for code in actual_sells:
            final_weights.pop(code, None)

        # 4. 归一化
        total = sum(final_weights.values())
        if total > 0:
            final_weights = {k: v / total for k, v in final_weights.items()}

        result.final_weights = final_weights

        if actual_sells or actual_buys:
            result.need_rebalance = True
            result.sells = list(actual_sells)
            result.buys = list(actual_buys)

    @staticmethod
    def _format_skip_reason(ev: dict, scores: dict[str, float]) -> str:
        """格式化跳过原因"""
        if ev["cost"] == float("inf"):
            return f"持有{ev['hold_days']}天 < 最小持有期，强制保留"
        return (
            f"成本{ev['cost']:.2%} > 预期收益提升{ev['benefit']:.2%}, "
            f"净收益{ev['net_benefit']:.2%}"
        )


@register_rebalancer("simple")
class SimpleRebalancer(BaseRebalancer):
    """简单调仓器

    直接采用目标权重，不做成本收益权衡。仅计算交易成本。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = config or {}
        cost_model_cfg = cfg.get("cost_model", {"name": "stock_cn"})
        if isinstance(cost_model_cfg, str):
            cost_model_cfg = {"name": cost_model_cfg}
        self.cost_model: BaseCostModel = create_cost_model(cost_model_cfg)

    def decide(
        self,
        current_weights: WeightMap,
        target_weights: WeightMap,
        hold_days_map: dict[str, int] | None = None,
        scores: dict[str, float] | None = None,
    ) -> RebalanceResult:
        old_codes = set(current_weights)
        new_codes = set(target_weights)

        sells = list(old_codes - new_codes)
        buys = list(new_codes - old_codes)
        cost = self.cost_model.estimate(current_weights, target_weights, hold_days_map)

        return RebalanceResult(
            need_rebalance=bool(sells or buys) or not current_weights,
            sells=sells,
            buys=buys,
            total_cost=cost,
            final_weights=dict(target_weights),
        )


@register_rebalancer("none")
class NoOpRebalancer(BaseRebalancer):
    """空操作调仓器

    不调仓，final_weights = current_weights。成本模型为 None。
    用于回测中保持向后兼容（method == "none" 时走 Phase 4 的 flat cost 逻辑）。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.cost_model: BaseCostModel | None = None

    def decide(
        self,
        current_weights: WeightMap,
        target_weights: WeightMap,
        hold_days_map: dict[str, int] | None = None,
        scores: dict[str, float] | None = None,
    ) -> RebalanceResult:
        return RebalanceResult(
            need_rebalance=False,
            final_weights=dict(current_weights),
        )


def create_rebalancer(config: dict | None = None) -> BaseRebalancer:
    """工厂方法：根据配置创建调仓器

    Args:
        config: 调仓配置 dict，需包含 method 字段指定调仓器类型。
                method 可选: cost_benefit / simple / none
                未指定 method 时默认 cost_benefit

    Returns:
        BaseRebalancer 实例
    """
    from ..core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    method = cfg.get("method", "cost_benefit")
    return PluginRegistry.create(PluginType.REBALANCER, method, config=cfg)


__all__ = [
    "CostBenefitRebalancer",
    "SimpleRebalancer",
    "NoOpRebalancer",
    "create_rebalancer",
]
