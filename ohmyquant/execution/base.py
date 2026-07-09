"""调仓器基类

可插拔调仓接口，参考 ETF_portfolio 的 Rebalancer。
所有调仓插件实现此接口，通过统一 register_rebalancer 装饰器注册。

配置中通过 rebalance.method 切换:
  method: cost_benefit → CostBenefitRebalancer（成本收益权衡）
  method: simple       → SimpleRebalancer（直接采用目标权重）
  method: none         → NoOpRebalancer（不调仓）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.types import WeightMap


@dataclass
class RebalanceResult:
    """调仓决策结果

    Attributes:
        need_rebalance: 是否需要调仓
        sells: 卖出标的代码列表
        buys: 买入标的代码列表
        skipped_sells: 跳过的卖出（成本过高），每项含 code/hold_days/cost/benefit/reason
        total_cost: 总交易成本（占总资产比例）
        total_benefit: 预期收益提升（评分差 × 系数）
        final_weights: 实际执行后的权重（含跳过的卖出标的，已归一化）
    """

    need_rebalance: bool = False
    sells: list[str] = field(default_factory=list)
    buys: list[str] = field(default_factory=list)
    skipped_sells: list[dict] = field(default_factory=list)
    total_cost: float = 0.0
    total_benefit: float = 0.0
    final_weights: WeightMap = field(default_factory=dict)

    @property
    def net_benefit(self) -> float:
        """净收益 = 预期收益提升 - 总成本"""
        return self.total_benefit - self.total_cost


class BaseRebalancer(ABC):
    """调仓器抽象基类

    子类实现 decide() 方法，根据当前持仓和目标持仓决定是否调仓及具体买卖标的。

    N 资产架构：不局限于固定数量标的，支持任意数量。
    权重格式：dict[str, float]，{code: weight}，权重和为 1.0。
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.cost_benefit_threshold: float = cfg.get("cost_benefit_threshold", 0.0)
        self.min_hold_days: int = cfg.get("min_hold_days", 0)

    @abstractmethod
    def decide(
        self,
        current_weights: WeightMap,
        target_weights: WeightMap,
        hold_days_map: dict[str, int] | None = None,
        scores: dict[str, float] | None = None,
    ) -> RebalanceResult:
        """调仓决策

        Args:
            current_weights: 当前持仓权重 {code: weight}
            target_weights: 目标持仓权重 {code: weight}
            hold_days_map: 各标的持有天数 {code: hold_days}
            scores: 各标的评分 {code: score}（用于估算收益提升）

        Returns:
            RebalanceResult
        """
        ...


__all__ = ["RebalanceResult", "BaseRebalancer"]
