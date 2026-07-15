"""ML 选因子策略 v4

基于 v2 (k25_w1008) 扩展候选股票池：
  - 候选池: 沪深300 → 中证800 (000819.XSHG)
  - 中证800 = 沪深300 + 中证500，800只大中盘股票
  - 解决 v2 金融行业占比 70% 的集中度问题
  - 避免全A股小微股流动性问题

其余配置（ML选因子、ICIR选股、风控、调仓）与 v2 完全一致。
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v4")
class MLFStrategyV4(BaseStrategy):
    """ML 选因子策略 v4：中证800候选池 (k25_w1008_csi800)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV4":
        if strategy_type != "mlf" or version != "v4":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v4",
            "strategy_name": "ML选因子策略 v4",
            "description": "v2+扩展池：中证800候选池(k25_w1008_csi800)",
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
            "pools": {"stocks": {"index": "000819.XSHG"}},
            "data": {
                "source": "duckdb",
                "data_root": "D:/Work/Project/download_a_share/data",
            },
        }

        if config:
            base_config.update(config)

        return cls(base_config)
