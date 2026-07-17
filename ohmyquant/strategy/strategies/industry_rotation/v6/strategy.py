"""行业轮动策略 v6（低beta因子增强）

v5 问题：OOS分析发现持仓股票 beta 过高（1.44），下跌市回撤大于沪深300
v6 改进：
  - 在 v5 的10因子基础上加入2个反向风险因子：
    - raw_beta（反向，w=-1.5）：直接降低持仓 beta
    - residual_volatility（反向，w=-1.0）：BARRA残差波动率
  - 其他配置与 v5 完全相同

因子组合:
  动量(3): Price1M, Price3M, ROC20
  成交量(2): DAVOL10, money_flow_20
  质量(3): gross_income_ratio, roe_ttm, net_profit_ratio
  价值(2): earnings_to_price_ratio, book_to_price_ratio
  风险(2): raw_beta(反向), residual_volatility(反向)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v6")
class IndustryRotationStrategyV6(BaseStrategy):
    """行业轮动策略 industry_rotation_v6 (mf12_lowbeta_mom60_120_mkt20, final)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV6":
        if strategy_type != "industry_rotation" or version != "v6":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v6",
            "strategy_name": "行业轮动策略 industry_rotation_v6 (mf12_lowbeta_mom60_120_mkt20, final)",
            "description": "低beta因子增强:12因子(含2反向风险)+60/120日行业动量+大盘20日过滤+沪深300 [final]",
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
                    "market_ma_short": 10,
                    "market_ma_long": 20,
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
                        "raw_beta": -1.5,
                        "residual_volatility": -1.0,
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
