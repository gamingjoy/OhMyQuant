"""行业轮动策略 v10（残差动量 + 中证500候选池）

A方向：基于华泰金工《残差动量行业轮动》思路
研报参考：年化超额12.90%

v10 相对 v9 的改进：
1. 候选池：沪深300 → 中证500（D方向对比IS Sharpe 0.2256→0.6404，+65.42%收益）
2. 新增残差动量（Residual Momentum）：
   - residual_return = stock_return - raw_beta * market_return
   - 剔除市场Beta暴露后的特异性动量
   - 避免高Beta股虚假动量（牛市中高Beta股看起来动量强但只是市场Beta）
   - 用聚宽预计算的 raw_beta 因子做正交化

设计思路：
- 中证500候选池：中盘股行业分布更均衡，轮动机会更多
- 残差动量：剔除市场Beta后选"真正强势"的行业
- 保留v9所有防御机制：12因子选股、RRG、绝对动量、大盘过滤、行业风险过滤

因子组合（与v9一致）：
  动量(3): Price1M, Price3M, ROC20
  成交量(2): DAVOL10, money_flow_20
  质量(3): gross_income_ratio, roe_ttm, net_profit_ratio
  价值(2): earnings_to_price_ratio, book_to_price_ratio
  风险(2): raw_beta(反向,w=-2.0), residual_volatility(反向,w=-1.5)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v10")
class IndustryRotationStrategyV10(BaseStrategy):
    """行业轮动策略 industry_rotation_v10 (residual_mom_csi500_rrg220_30, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV10":
        if strategy_type != "industry_rotation" or version != "v10":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v10",
            "strategy_name": "行业轮动策略 industry_rotation_v10 (residual_mom_csi500_rrg220_30, iter)",
            "description": "残差动量+中证500候选池:12因子+RRG+绝对动量+残差动量(剔除市场Beta)+行业风险过滤 [iter]",
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
                    "market_index": "000905.XSHG",  # 中证500
                    "market_ma_short": 5,
                    "market_ma_long": 20,
                    "industry_risk_filter": True,
                    "risk_filter_window": 20,
                    "risk_filter_min_industries": 3,
                    "absolute_momentum": True,
                    "absolute_momentum_window": 20,
                    "absolute_momentum_threshold": -0.03,
                    "absolute_momentum_scale": 0.5,
                    "use_inv_vol_weight": False,
                    "inv_vol_window": 20,
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    # 残差动量（NEW in v10, 华泰金工）
                    "use_residual_momentum": True,
                    "residual_beta_factor": "raw_beta",
                    "residual_beta_default": 1.0,
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
            "pools": {"stocks": {"index": "000905.XSHG"}},  # 中证500
            "data": {
                "source": "duckdb",
                "data_root": "D:/Work/Project/download_a_share/data",
            },
        }

        if config:
            base_config.update(config)

        return cls(base_config)
