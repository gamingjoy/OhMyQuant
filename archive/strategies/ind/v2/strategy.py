"""行业轮动策略 v2（周频+波动率目标）

v1 问题：日频调仓换手成本高 + drawdown 风控过度降仓（总仓位仅45%）→ -6.27%
v2 改进：
  - 调仓频率：daily → weekly（每周一，减少换手成本）
  - 风控方法：drawdown → vol_target（避免回撤过度降仓）
  - 目标波动率：0.20 → 0.15（适度降仓控制风险）
  - 其余选股逻辑不变（20+60日动量，Top5行业×2股）
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("ind", "v2")
class IndRotationStrategyV2(BaseStrategy):
    """行业轮动策略 v2：周频调仓+波动率目标 (mom20_60_top5_ind2_csi300_weekly)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndRotationStrategyV2":
        if strategy_type != "ind" or version != "v2":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "ind",
            "strategy_version": "v2",
            "strategy_name": "行业轮动策略 v2",
            "description": "周频调仓+波动率目标：20+60日动量,Top5行业×2股,沪深300,vol_target0.15",
            "backtest": {
                "start_date": "2022-01-01",
                "end_date": "2025-12-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "ind",
                "top_n": 10,
                "max_stock_weight": 0.10,
                "ind": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_industries": 5,
                    "stocks_per_industry": 2,
                    "momentum_short": 20,
                    "momentum_long": 60,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,
                },
            },
            "portfolio": {
                "max_stock_weight": 0.10,
                "max_industry_weight": 0.30,
                "min_stocks": 5,
            },
            "risk": {
                "method": "vol_target",
                "target_vol": 0.15,
                "lookback": 20,
                "min_exposure_scale": 0.5,
            },
            "rebalance": {
                "frequency": "weekly",
                "weekday": 0,
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
