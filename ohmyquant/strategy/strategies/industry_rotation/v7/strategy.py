"""行业轮动策略 v7（行业短期风险过滤+严控风险）

v6 问题：行业选择仅基于60+120日中长期动量，板块开始下跌时中长期动量仍为正，
         无法及时规避高风险板块（如OOS期间持续持有有色金属）
v7 改进：
  - 新增行业短期风险过滤：用20日短期动量剔除近期下跌的行业
    （当中长期动量仍为正但短期已转负时，及时退出）
  - 强化反向风险因子：raw_beta -1.5→-2.0，residual_volatility -1.0→-1.5
  - 降低行业集中度：max_industry_weight 0.30→0.25（分散风险）
  - 大盘过滤更敏感：market_ma_short 10→5（更快响应下跌）
  - 因子组合保持 v6 的12因子

因子组合:
  动量(3): Price1M, Price3M, ROC20
  成交量(2): DAVOL10, money_flow_20
  质量(3): gross_income_ratio, roe_ttm, net_profit_ratio
  价值(2): earnings_to_price_ratio, book_to_price_ratio
  风险(2): raw_beta(反向,w=-2.0), residual_volatility(反向,w=-1.5)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v7")
class IndustryRotationStrategyV7(BaseStrategy):
    """行业轮动策略 industry_rotation_v7 (mf12_lowbeta_riskfilter20_mkt5, final)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV7":
        if strategy_type != "industry_rotation" or version != "v7":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v7",
            "strategy_name": "行业轮动策略 industry_rotation_v7 (mf12_lowbeta_riskfilter20_mkt5, final)",
            "description": "行业风险过滤+严控风险:12因子(含2反向风险)+20日行业风险过滤+大盘5/20日+沪深300 [final]",
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
                    "max_industry_weight": 0.25,
                    "market_filter": True,
                    "market_index": "000300.XSHG",
                    "market_ma_short": 5,
                    "market_ma_long": 20,
                    # 行业短期风险过滤：剔除20日内下跌的行业
                    "industry_risk_filter": True,
                    "risk_filter_window": 20,
                    "risk_filter_min_industries": 3,
                    "use_factors": True,
                    "factor_names": [
                        "Price1M", "Price3M", "ROC20",
                        "DAVOL10", "money_flow_20",
                        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
                        "earnings_to_price_ratio", "book_to_price_ratio",
                        "raw_beta", "residual_volatility",
                    ],
                    "factor_weights": {
                        "Price1M": 1.0, "Price3M": 1.0, "ROC20": 1.0,
                        "DAVOL10": 1.0, "money_flow_20": 1.0,
                        "gross_income_ratio": 1.0, "roe_ttm": 1.0,
                        "net_profit_ratio": 1.0,
                        "earnings_to_price_ratio": 1.0,
                        "book_to_price_ratio": 1.0,
                        "raw_beta": -2.0,
                        "residual_volatility": -1.5,
                    },
                },
            },
            "portfolio": {
                "max_stock_weight": 0.10,
                "max_industry_weight": 0.25,
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
