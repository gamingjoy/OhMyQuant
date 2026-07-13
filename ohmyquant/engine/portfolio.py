"""组合约束优化器

独立处理组合约束，参考 halo_index 的 PortfolioOptimizer。
改为操作 dict[str, float] 权重格式（code → weight）。

支持的约束:
  - 个股权重上限 (max_stock_weight)
  - 行业权重上限 (max_industry_weight)
  - 换手率限制 (max_turnover)
  - 最少持仓数 (min_stocks)
  - 权重截断迭代次数 (weight_cap_iterations)
"""
from __future__ import annotations

from ..core.logging import get_logger

logger = get_logger(__name__)


class PortfolioOptimizer:
    """组合约束优化器

    用法:
        po = PortfolioOptimizer({"max_stock_weight": 0.025, "max_industry_weight": 0.15})
        weights = po.optimize(
            weights={"a": 0.10, "b": 0.08, ...},
            old_weights={"a": 0.05, "c": 0.03, ...},
            industry_map={"a": "银行", "b": "地产", ...},
        )
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        portfolio_cfg = cfg.get("portfolio", cfg)  # 兼容两种传入方式

        self.max_stock_weight: float = portfolio_cfg.get("max_stock_weight", 0.025)
        self.max_industry_weight: float = portfolio_cfg.get("max_industry_weight", 0.15)
        self.max_turnover: float = portfolio_cfg.get("max_turnover", 0.5)
        self.min_stocks: int = portfolio_cfg.get("min_stocks", 10)
        self.cap_iterations: int = portfolio_cfg.get("weight_cap_iterations", 10)

    def apply_weight_cap(
        self,
        weights: dict[str, float],
        cap: float | None = None,
    ) -> dict[str, float]:
        """应用个股权重上限，超出部分按比例再分配给未超限个股

        Args:
            weights: {code: weight}
            cap: 权重上限，None 则用 self.max_stock_weight

        Returns:
            处理后的权重
        """
        cap = cap or self.max_stock_weight
        if not weights:
            return weights

        result = dict(weights)

        for _ in range(self.cap_iterations):
            over_cap = {k: v for k, v in result.items() if v > cap}
            if not over_cap:
                break

            excess = sum(v - cap for v in over_cap.values())
            for k in over_cap:
                result[k] = cap

            under_cap = {k: v for k, v in result.items() if v < cap}
            if under_cap:
                under_total = sum(under_cap.values())
                if under_total > 0:
                    for k in under_cap:
                        result[k] += excess * (under_cap[k] / under_total)
                        result[k] = min(result[k], cap)

        # 最终归一化
        total = sum(result.values())
        if total > 0:
            result = {k: v / total for k, v in result.items()}

        return result

    def apply_industry_cap(
        self,
        weights: dict[str, float],
        industry_map: dict[str, str],
        cap: float | None = None,
    ) -> dict[str, float]:
        """应用行业权重上限，超出部分按比例缩减

        Args:
            weights: {code: weight}
            industry_map: {code: industry_name}
            cap: 行业权重上限，None 则用 self.max_industry_weight

        Returns:
            处理后的权重
        """
        cap = cap or self.max_industry_weight
        if cap >= 1.0 or not weights:
            return weights

        # 按行业聚合
        industry_weights: dict[str, float] = {}
        for code, w in weights.items():
            ind = industry_map.get(code, "未知")
            industry_weights[ind] = industry_weights.get(ind, 0) + w

        # 缩减超限行业
        result = dict(weights)
        for ind, total_w in industry_weights.items():
            if total_w > cap:
                scale = cap / total_w
                for code in result:
                    if industry_map.get(code, "未知") == ind:
                        result[code] *= scale

        return result

    def apply_turnover_limit(
        self,
        new_weights: dict[str, float],
        old_weights: dict[str, float],
        max_turnover: float | None = None,
    ) -> dict[str, float]:
        """应用换手率限制

        Args:
            new_weights: 目标权重 {code: weight}
            old_weights: 当前权重 {code: weight}
            max_turnover: 单边换手率上限，None 则用 self.max_turnover

        Returns:
            调整后的权重
        """
        max_turnover = max_turnover or self.max_turnover
        if max_turnover >= 1.0:
            return new_weights

        all_codes = set(new_weights) | set(old_weights)
        turnover = 0.0
        for code in all_codes:
            turnover += abs(new_weights.get(code, 0) - old_weights.get(code, 0))
        turnover /= 2  # 单边换手率

        if turnover <= max_turnover:
            return new_weights

        # 按比例缩减换手
        scale = max_turnover / turnover
        adjusted: dict[str, float] = {}
        for code in all_codes:
            old_w = old_weights.get(code, 0)
            new_w = new_weights.get(code, 0)
            w = old_w + (new_w - old_w) * scale
            if w > 1e-6:
                adjusted[code] = w

        return adjusted

    def enforce_min_stocks(
        self,
        weights: dict[str, float],
        min_stocks: int | None = None,
    ) -> dict[str, float]:
        """检查最少持仓数（仅警告，不自动填充）

        Args:
            weights: {code: weight}
            min_stocks: 最小持仓数，None 则用 self.min_stocks

        Returns:
            原权重（不修改）
        """
        min_stocks = min_stocks or self.min_stocks
        active = sum(1 for w in weights.values() if w > 1e-6)
        if active < min_stocks:
            logger.warning(
                f"持仓数 {active} 少于最小要求 {min_stocks}，"
                f"可能影响分散度"
            )
        return weights

    def optimize(
        self,
        weights: dict[str, float],
        old_weights: dict[str, float] | None = None,
        industry_map: dict[str, str] | None = None,
    ) -> dict[str, float]:
        """执行全部组合约束优化

        顺序:
          1. 个股权重上限
          2. 行业权重上限
          3. 换手率限制（需 old_weights）
          4. 最少持仓数检查
          5. 移除零权重

        Args:
            weights: 新持仓权重 {code: weight}
            old_weights: 旧持仓权重（用于换手率限制），可选
            industry_map: 行业映射 {code: industry}，可选

        Returns:
            优化后的权重
        """
        # 1. 个股权重上限
        result = self.apply_weight_cap(weights)

        # 2. 行业权重上限
        if industry_map:
            result = self.apply_industry_cap(result, industry_map)

        # 3. 换手率限制
        if old_weights is not None:
            result = self.apply_turnover_limit(result, old_weights)

        # 4. 最少持仓数检查
        result = self.enforce_min_stocks(result)

        # 5. 移除零权重
        result = {k: v for k, v in result.items() if v > 1e-6}

        return result


__all__ = ["PortfolioOptimizer"]
