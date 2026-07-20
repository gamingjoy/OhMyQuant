"""行业轮动策略 v18（动量维度扩展：短/中/长周期动量组合）

v18 = v15 + 4个长期动量因子（共16个因子）

设计目的：
  v15 的3个动量因子（Price1M, Price3M, ROC20）集中在短中期（1-3月）
  缺少长期动量（6月-1年），无法捕捉长期趋势
  加入长期动量可形成完整的动量期限结构

v18 新增4个动量因子：
  - Price1Y（1年价格动量，长期趋势）
  - ROC60（60日动量，中期补强）
  - ROC120（120日动量，中长期）
  - relative_strength（聚宽计算的相对强度）

研究假设：
  - 长期动量与短期动量正交，提供独立信号
  - 短期动量捕捉近期强势，长期动量过滤长期趋势
  - 完整动量期限结构（1M/3M/6M/12M）比单一期限更稳健

baseline: v15 (IS Sharpe 0.4030 / OOS Sharpe 1.7018 / OOS +3.32%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v18")
class IndustryRotationStrategyV18(BaseStrategy):
    """行业轮动策略 industry_rotation_v18 (multiperiod_rrg_pe_long_momentum_csi300, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV18":
        if strategy_type != "industry_rotation" or version != "v18":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v18",
            "strategy_name": "行业轮动策略 industry_rotation_v18 (multiperiod_rrg_pe_long_momentum_csi300, iter)",
            "description": "多周期RRG+PE过滤+长期动量扩展:16因子(12+4新)+沪深300 [iter]",
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
                    "industry_risk_filter": True,
                    "risk_filter_window": 20,
                    "risk_filter_min_industries": 3,
                    "absolute_momentum": True,
                    "absolute_momentum_window": 20,
                    "absolute_momentum_threshold": -0.03,
                    "absolute_momentum_scale": 0.5,
                    "use_inv_vol_weight": False,
                    "inv_vol_window": 20,
                    # RRG 多周期投票（同 v15）
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,
                    "rs_momentum_windows": [10, 30, 60],
                    "rs_momentum_vote_threshold": 2,
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    # 行业估值过滤（同 v15）
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
                    "use_factors": True,
                    # 16 因子 = v15的12 + 新增4（长期动量）
                    "factor_names": [
                        # v15 原有12因子
                        "Price1M", "Price3M", "ROC20",
                        "DAVOL10", "money_flow_20",
                        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
                        "earnings_to_price_ratio", "book_to_price_ratio",
                        "raw_beta", "residual_volatility",
                        # v18 新增4个长期动量因子
                        "Price1Y", "ROC60", "ROC120", "relative_strength",
                    ],
                    "factor_weights": {
                        # v15 原有12因子权重
                        "Price1M": 1.0, "Price3M": 1.0, "ROC20": 1.0,
                        "DAVOL10": 1.0, "money_flow_20": 1.0,
                        "gross_income_ratio": 1.0, "roe_ttm": 1.0,
                        "net_profit_ratio": 1.0,
                        "earnings_to_price_ratio": 1.0,
                        "book_to_price_ratio": 1.0,
                        "raw_beta": -2.0,
                        "residual_volatility": -1.5,
                        # v18 新增4个长期动量因子权重（等权1.0）
                        "Price1Y": 1.0,
                        "ROC60": 1.0,
                        "ROC120": 1.0,
                        "relative_strength": 1.0,
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
