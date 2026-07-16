"""ML 选因子策略 v3

基于 v2 (k25_w1008) 调整组合约束：
  - max_stock_weight: 4% → 2.5%（降低集中度，提升分散化）
  - top_n: 30 → 50（适配 2.5% 上限，确保满仓）

其余配置（ML选因子、ICIR选股、风控、调仓）与 v2 完全一致。

OOS 表现待回测确认。
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v3")
class MLFStrategyV3(BaseStrategy):
    """ML 选因子策略 v3：v2 基础上降低单股权重上限至 2.5% (k25_w1008_w025)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV3":
        if strategy_type != "mlf" or version != "v3":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v3",
            "strategy_name": "ML选因子策略 v3",
            "description": "v2+分散化：2.5%权重上限+50只股票(k25_w1008_w025)",
            "backtest": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.0008,
            },
            "selection": {
                "method": "mlf",
                "top_n": 50,
                "max_stock_weight": 0.025,
                "mlf": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_k_factors": 25,
                    "train_window": 1008,
                    "retrain_freq": 21,
                    "target_horizon": 20,
                    "neutralize": True,
                },
            },
            "risk": {
                "method": "vol_target",
                "target_vol": 0.18,
                "lookback": 20,
                "min_exposure_scale": 0.5,
            },
            "rebalance": {
                "frequency": "monthly",
                "method": "cost_benefit",
                "cost_model": {"name": "stock_cn"},
            },
            "factors": ["mom_1m"],
            "pools": {"stocks": {"index": "000300.XSHG"}},
            "data": {
                "source": "duckdb",
                "data_root": "D:/Work/Project/download_a_share/data",
            },
        }

        if config:
            base_config.update(config)

        return cls(base_config)
