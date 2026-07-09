"""交易成本模型

可插拔成本接口，支持股票和 ETF 两类市场的真实成本计算。

配置中通过 rebalance.cost_model.name 切换:
  name: stock_cn → StockCostModel（A股：佣金+印花税+过户费）
  name: etf_cn   → ETFCostModel（ETF：申购费+赎回费，7天内惩罚性费率）

参考 ETF_portfolio 的 CostModel，泛化到 WeightMap 权重格式。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.plugin_system import register_cost_model
from ..core.types import WeightMap


class BaseCostModel(ABC):
    """成本模型抽象基类

    子类实现 buy_cost() / sell_cost() / estimate() 方法。
    estimate() 基于 buy_cost/sell_cost 的默认实现，子类通常无需重写。
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def buy_cost(self, weight: float, code: str | None = None) -> float:
        """买入成本（占总资产比例）

        Args:
            weight: 买入权重（如 0.1 表示买入 10% 仓位）
            code: 标的代码（混合成本模型按此选择费率）

        Returns:
            成本占总资产比例
        """
        ...

    @abstractmethod
    def sell_cost(self, weight: float, hold_days: int = 0, code: str | None = None) -> float:
        """卖出成本（占总资产比例）

        Args:
            weight: 卖出权重
            hold_days: 持有天数（部分市场如 ETF 短期持有有惩罚费率）
            code: 标的代码（混合成本模型按此选择费率）

        Returns:
            成本占总资产比例
        """
        ...

    def estimate(
        self,
        old_weights: WeightMap,
        new_weights: WeightMap,
        hold_days_map: dict[str, int] | None = None,
    ) -> float:
        """估算调仓成本（占总资产比例）

        遍历所有标的，权重增加用 buy_cost，权重减少用 sell_cost。

        Args:
            old_weights: 旧持仓权重 {code: weight}
            new_weights: 新持仓权重 {code: weight}
            hold_days_map: 各标的持有天数 {code: hold_days}，可选

        Returns:
            总成本占总资产比例
        """
        hold_days_map = hold_days_map or {}
        total_cost = 0.0

        all_codes = set(old_weights) | set(new_weights)
        for code in all_codes:
            old_w = old_weights.get(code, 0.0)
            new_w = new_weights.get(code, 0.0)
            delta = new_w - old_w

            if delta > 1e-9:
                total_cost += self.buy_cost(delta, code)
            elif delta < -1e-9:
                total_cost += self.sell_cost(-delta, hold_days_map.get(code, 0), code)

        return total_cost


@register_cost_model("stock_cn")
class StockCostModel(BaseCostModel):
    """A股成本模型

    买入：佣金 + 过户费
    卖出：佣金 + 印花税 + 过户费

    默认费率（可配置）:
      commission_rate: 0.00025  （万2.5，券商佣金）
      stamp_duty:      0.0005   （印花税，卖出单边）
      transfer_fee:    0.00001  （过户费，沪深均收）
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = self.config
        self.commission_rate: float = cfg.get("commission_rate", 0.00025)
        self.stamp_duty: float = cfg.get("stamp_duty", 0.0005)
        self.transfer_fee: float = cfg.get("transfer_fee", 0.00001)

    def buy_cost(self, weight: float, code: str | None = None) -> float:
        return weight * (self.commission_rate + self.transfer_fee)

    def sell_cost(self, weight: float, hold_days: int = 0, code: str | None = None) -> float:
        return weight * (self.commission_rate + self.stamp_duty + self.transfer_fee)


@register_cost_model("etf_cn")
class ETFCostModel(BaseCostModel):
    """ETF 成本模型（C 类份额）

    买入：申购费（C 类通常为 0）
    卖出：赎回费，持有 < min_hold_days 天为惩罚性费率，否则为 0

    默认费率（可配置）:
      purchase_fee:          0.0    （申购费，C类为0）
      redeem_fee_within_7d:  0.015  （7天内赎回费1.5%）
      redeem_fee_after_7d:   0.0    （7天后赎回费0%）
      min_hold_days:         7      （最小持有天数）
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = self.config
        self.purchase_fee: float = cfg.get("purchase_fee", 0.0)
        self.redeem_fee_within_7d: float = cfg.get("redeem_fee_within_7d", 0.015)
        self.redeem_fee_after_7d: float = cfg.get("redeem_fee_after_7d", 0.0)
        self.min_hold_days: int = cfg.get("min_hold_days", 7)

    def buy_cost(self, weight: float, code: str | None = None) -> float:
        return weight * self.purchase_fee

    def sell_cost(self, weight: float, hold_days: int = 0, code: str | None = None) -> float:
        if hold_days < self.min_hold_days:
            return weight * self.redeem_fee_within_7d
        return weight * self.redeem_fee_after_7d


@register_cost_model("mixed_cn")
class MixedCostModel(BaseCostModel):
    """混合成本模型：按标的类型自动选择 stock_cn / etf_cn

    用于 A股+ETF 混合策略，根据代码前缀自动判断资产类型。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.stock_model = StockCostModel(config)
        self.etf_model = ETFCostModel(config)

    @staticmethod
    def _is_etf(code: str | None) -> bool:
        """判断是否为 ETF 代码

        ETF 代码前缀: 51/15/16/52/56/59 开头（上交所/深交所 ETF）
        """
        if not code or "." not in code:
            return False
        prefix = code.split(".")[0]
        return prefix[:2] in ("51", "15", "16", "52", "56", "59")

    def buy_cost(self, weight: float, code: str | None = None) -> float:
        if self._is_etf(code):
            return self.etf_model.buy_cost(weight, code)
        return self.stock_model.buy_cost(weight, code)

    def sell_cost(self, weight: float, hold_days: int = 0, code: str | None = None) -> float:
        if self._is_etf(code):
            return self.etf_model.sell_cost(weight, hold_days, code)
        return self.stock_model.sell_cost(weight, hold_days, code)


def create_cost_model(config: dict | None = None) -> BaseCostModel:
    """工厂方法：根据配置创建成本模型

    Args:
        config: 成本模型配置 dict，需包含 name 字段指定类型。
                name 可选: stock_cn / etf_cn
                未指定 name 时默认 stock_cn

    Returns:
        BaseCostModel 实例
    """
    from ..core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    name = cfg.get("name", "stock_cn")
    return PluginRegistry.create(PluginType.COST_MODEL, name, config=cfg)


__all__ = [
    "BaseCostModel",
    "StockCostModel",
    "ETFCostModel",
    "MixedCostModel",
    "create_cost_model",
]
