"""行业轮动策略 v25（+现金流估值因子cash_earnings_to_price_ratio）—— [ITER]

状态: iter（试验中，2026-07-20）
baseline: v23 (IS Sharpe 0.4476 / OOS Sharpe 2.4951 / OOS +5.39%)

v25 = v23 + 新增 cash_earnings_to_price_ratio（13个因子）

设计目的：
  v23 已有 earnings_to_price_ratio（净利润/市值，1/PE）
  v25 加入 cash_earnings_to_price_ratio（经营现金流/市值，CEP）
  形成"盈利+现金流"双重价值筛选
  现金流比会计盈利更难操纵，能识别"会计盈利高但现金流差"的公司

理论依据：
  - CEP = CFO / Market Cap
  - 高CEP公司有真实现金流支撑，盈利质量高
  - 学术研究（Sloan 1996）发现现金流比盈利更具持续性
  - 与earnings_to_price_ratio互补：E/P可能被操纵，CEP不会

v25 改进：
  - factor_names 新增 cash_earnings_to_price_ratio
  - factor_weights: cash_earnings_to_price_ratio: 1.0
  - 其他配置同 v23

baseline: v23 (IS Sharpe 0.4476 / OOS Sharpe 2.4951 / OOS +5.39%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v25")
class IndustryRotationStrategyV25(BaseStrategy):
    """行业轮动策略 industry_rotation_v25 (multiperiod_rrg_pe_top3_stocks3_cep, iter)

    状态: iter（试验中，2026-07-20）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV25":
        if strategy_type != "industry_rotation" or version != "v25":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v25",
            "strategy_name": "行业轮动策略 industry_rotation_v25 (multiperiod_rrg_pe_top3_stocks3_cep, iter)",
            "description": "多周期RRG+PE过滤+Top-3行业每行业3股+现金流估值:13因子+沪深300 [iter]",
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
                    "top_industries": 3,
                    "stocks_per_industry": 3,
                    "momentum_short": 60,
                    "momentum_long": 120,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,
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
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,
                    "rs_momentum_windows": [10, 30, 60],
                    "rs_momentum_vote_threshold": 2,
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
                    "use_factors": True,
                    "factor_names": [
                        "Price1M", "Price3M", "ROC20",
                        "DAVOL10", "money_flow_20",
                        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
                        "earnings_to_price_ratio", "book_to_price_ratio",
                        "raw_beta", "residual_volatility",
                        "cash_earnings_to_price_ratio",  # NEW in v25: 现金流估值
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
                        "cash_earnings_to_price_ratio": 1.0,  # NEW: 现金流估值
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
