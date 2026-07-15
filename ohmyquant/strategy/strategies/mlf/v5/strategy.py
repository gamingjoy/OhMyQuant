"""ML 选因子策略 v5

基于 v2 (k25_w1008) 加入行业暴露约束：
  - max_industry_weight: 20%（单行业权重上限）
  - 解决 v2 金融行业占比 70% 的集中度问题
  - 超限行业缩放后，excess 权重 redistributed 到其他行业

其余配置与 v2 完全一致（沪深300, 4%单股上限, 30只股票）。
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v5")
class MLFStrategyV5(BaseStrategy):
    """ML 选因子策略 v5：v2 + 行业暴露约束 (k25_w1008_ind20)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV5":
        if strategy_type != "mlf" or version != "v5":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v5",
            "strategy_name": "ML选因子策略 v5",
            "description": "v2+行业中性：20%行业暴露上限(k25_w1008_ind20)",
            "backtest": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.0008,
            },
            "selection": {
                "method": "mlf",
                "top_n": 30,
                "max_stock_weight": 0.04,
                "mlf": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_k_factors": 25,
                    "train_window": 1008,
                    "retrain_freq": 21,
                    "target_horizon": 20,
                    "neutralize": True,
                    "max_industry_weight": 0.20,
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
