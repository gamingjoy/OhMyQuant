"""ML 选因子策略 v6

基于 v5 优化候选股票池 + 行业约束算法：
  - 候选池: 沪深300 → 中证800 (000819.XSHG，前800大中盘)
  - 中证800 = 沪深300 + 中证500，避免全A股小微股流动性问题
  - 行业配额选股: max_stocks_per_industry=5，确保至少6个行业
  - 行业权重上限: 20%（修复算法，尊重个股权重上限）
  - 更大候选池 + 行业配额 → 行业多样性 + 流动性

v4 (中证800无行业约束) 因有色金属集中 80% 而亏损 -9%，
v6 用行业配额(5只/行业) + 权重上限(20%) 解决集中度问题。
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v6")
class MLFStrategyV6(BaseStrategy):
    """ML 选因子策略 v6：中证800+行业配额 (k25_w1008_csi800_indq5)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV6":
        if strategy_type != "mlf" or version != "v6":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v6",
            "strategy_name": "ML选因子策略 v6",
            "description": "中证800+行业配额：5只/行业+20%权重上限(k25_w1008_csi800_indq5)",
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
            "pools": {"stocks": {"index": "000819.XSHG"}},
            "data": {
                "source": "duckdb",
                "data_root": "D:/Work/Project/download_a_share/data",
            },
        }

        if config:
            base_config.update(config)

        return cls(base_config)
