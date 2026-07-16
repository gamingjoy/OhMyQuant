"""ML 选因子策略 v7

基于 v5 (沪深300+行业约束) 优化选股多样性：
  - 候选池: 沪深300 (保持不变，ML 模型在沪深300上表现最好)
  - 行业配额选股: max_stocks_per_industry=5，确保至少6个行业
  - 行业权重上限: 20%（修复算法，尊重个股权重上限）
  - 5只/行业 × 4%上限 = 20%行业上限（自然满足，无现金拖累）

v6 (中证800+配额) 因 ML 模型在更大池中选出有色金属（OOS崩盘）而亏损。
v7 回归沪深300 + 行业配额，保持 ML 预测质量 + 提升多样性。
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v7")
class MLFStrategyV7(BaseStrategy):
    """ML 选因子策略 v7：沪深300+行业配额 (k25_w1008_csi300_indq5)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV7":
        if strategy_type != "mlf" or version != "v7":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v7",
            "strategy_name": "ML选因子策略 v7",
            "description": "沪深300+行业配额：5只/行业(k25_w1008_csi300_indq5)",
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
                    "max_stocks_per_industry": 5,
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
