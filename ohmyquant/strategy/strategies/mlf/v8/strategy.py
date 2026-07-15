"""ML 选因子策略 v8

基于 v5 超参网格搜索最优配置 (收益最高)：
  - top_n: 30 → 20 (更集中，ML top-20 挑选质量更高)
  - top_k_factors: 25 → 30 (更多因子，因子多样性)
  - max_industry_weight: 0.20 → 0.25 (更松约束，减少现金拖累)

网格搜索 27 组合中收益最高: +11.65%, Sharpe 5.39, 回撤 -4.65%
v5 基线 (n30_k25_ind20): +10.64%, Sharpe 5.32, 回撤 -4.30%

关键发现:
  - 更少股票 (20) + 更多因子 (30) = 更高收益
  - 更松行业约束 (25%) = 更少现金拖累
  - 4% 单股上限 × 20 只 = 80% 最大仓位，剩余为现金
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v8")
class MLFStrategyV8(BaseStrategy):
    """ML 选因子策略 v8：网格搜索最优 (k30_w1008_csi300_n20_ind25)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV8":
        if strategy_type != "mlf" or version != "v8":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v8",
            "strategy_name": "ML选因子策略 v8",
            "description": "网格搜索最优：20只股票+30因子+25%行业(k30_w1008_csi300_n20_ind25)",
            "backtest": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.0008,
            },
            "selection": {
                "method": "mlf",
                "top_n": 20,
                "max_stock_weight": 0.04,
                "mlf": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_k_factors": 30,
                    "train_window": 1008,
                    "retrain_freq": 21,
                    "target_horizon": 20,
                    "neutralize": True,
                    "max_industry_weight": 0.25,
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
