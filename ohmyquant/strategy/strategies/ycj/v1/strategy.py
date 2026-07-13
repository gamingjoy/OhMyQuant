"""YCJ 量化策略 v1

基于因子的量化策略，使用 ICIR 选股 + 等权分配 + 波动率目标风控。

配置说明：
  - 股票池：CSI 800
  - 因子：动量因子组合
  - 选股方法：ICIR
  - 池间分配：等权
  - 风控：波动率目标
  - 调仓频率：月度
"""
from __future__ import annotations

from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy import register_strategy


@register_strategy("ycj", "v1")
class YCJStrategyV1(BaseStrategy):
    """YCJ 量化策略 v1"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "YCJStrategyV1":
        """工厂方法"""
        if strategy_type != "ycj" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "ycj",
            "strategy_version": "v1",
            "strategy_name": "YCJ 量化策略 v1",
            "description": "基于 ICIR 选股的量化策略 v1",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "icir",
                "top_n": 50,
                "max_stock_weight": 0.02,
            },
            "risk": {
                "target_vol": 0.25,
            },
            "allocation": {
                "method": "equal",
            },
            "rebalance": {
                "frequency": "monthly",
                "method": "cost_benefit",
                "cost_model": {"name": "stock_cn"},
            },
            "factors": ["mom_1m", "mom_3m", "mom_6m"],
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
