"""行业轮动策略 v3（大盘过滤+长期动量+regime风控）

v2 问题：回撤大(-30.6%)，无大盘趋势过滤，纯动量在切换期回撤大
v3 改进：
  - 大盘趋势过滤：沪深300跌破20日均线降仓50%，跌破60日均线空仓
  - 长期动量：20+60日 → 60+120日（更稳定，减少噪音）
  - 风控方法：vol_target → regime_adaptive（结合波动率和趋势识别）
  - 调仓频率：周频（保持）
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v3")
class IndustryRotationStrategyV3(BaseStrategy):
    """行业轮动策略 v3：大盘过滤+长期动量 (mom60_120_top5_ind2_csi300_mktfilter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV3":
        if strategy_type != "industry_rotation" or version != "v3":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v3",
            "strategy_name": "行业轮动策略 v3",
            "description": "大盘过滤+长期动量：60+120日动量,Top5行业×2股,沪深300,大盘均线过滤,regime风控",
            "backtest": {
                "start_date": "2022-01-01",
                "end_date": "2025-12-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "industry_rotation",
                "top_n": 10,
                "max_stock_weight": 0.10,
                "industry_rotation": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_industries": 5,
                    "stocks_per_industry": 2,
                    "momentum_short": 60,
                    "momentum_long": 120,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,
                    "market_filter": True,
                    "market_index": "000300.XSHG",
                    "market_ma_short": 20,
                    "market_ma_long": 60,
                },
            },
            "portfolio": {
                "max_stock_weight": 0.10,
                "max_industry_weight": 0.30,
                "min_stocks": 5,
            },
            "risk": {
                "method": "regime_adaptive",
                "target_vol": 0.18,
                "lookback": 20,
                "min_exposure_scale": 0.3,
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
