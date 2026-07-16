"""行业轮动策略 v6（动量增强+低波因子）

v5 问题：质量/价值因子权重过高，削弱动量信号，收益下降
v6 改进：
  - 动量因子权重提升（Price1M:2.0, Price3M:2.0, ROC20:1.5）
  - 加入低波动因子（ATR14:-0.5, historical_sigma:-0.5，负权重=低波动优先）
  - 保留成交量因子（DAVOL10, money_flow_20）
  - 降低质量因子权重（roe_ttm:0.5）
  - 目标：恢复v4收益水平的同时保持v5的低回撤
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("ind", "v6")
class IndRotationStrategyV6(BaseStrategy):
    """行业轮动策略 v6：动量增强+低波 (mf8_mom_enhanced_lowvol_csi300_mkt20)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndRotationStrategyV6":
        if strategy_type != "ind" or version != "v6":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "ind",
            "strategy_version": "v6",
            "strategy_name": "行业轮动策略 v6",
            "description": "动量增强+低波：60+120日行业动量+8因子(动量增强+低波),大盘20日过滤",
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
                    "momentum_short": 60,
                    "momentum_long": 120,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,
                    "market_filter": True,
                    "market_index": "000300.XSHG",
                    "market_ma_short": 10,
                    "market_ma_long": 20,
                    "use_factors": True,
                    "factor_names": [
                        # 动量（高=好）
                        "Price1M", "Price3M", "ROC20",
                        # 成交量（高=好）
                        "DAVOL10", "money_flow_20",
                        # 低波动（低=好，用负权重）
                        "ATR14", "historical_sigma",
                        # 质量（高=好）
                        "roe_ttm",
                    ],
                    "factor_weights": {
                        "Price1M": 2.0,
                        "Price3M": 2.0,
                        "ROC20": 1.5,
                        "DAVOL10": 1.0,
                        "money_flow_20": 1.0,
                        "ATR14": -0.5,
                        "historical_sigma": -0.5,
                        "roe_ttm": 0.5,
                    },
                },
            },
            "portfolio": {
                "max_stock_weight": 0.10,
                "max_industry_weight": 0.30,
                "min_stocks": 5,
            },
            "risk": {
                "method": "regime_adaptive",
                "target_vol": 0.12,
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
