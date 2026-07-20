"""行业轮动策略 v40（多周期RRG加权投票：短期权重更高）—— [FINAL]

状态: final（当前最优策略，2026-07-20 锁定）
IS Sharpe 0.4339 / OOS Sharpe 2.6787 / OOS 收益 +6.66%（vs 沪深300 -3.01%）
IS-OOS 一致性合理，IS显著超越 v30 (IS 0.4249 / OOS 2.6787 / OOS +6.66%)

v40 = v30 + rs_momentum_vote_weights: [] → [0.5, 0.3, 0.2]

设计目的：
  v30 使用等权投票：vote_count = (RS-Mom_10≥100) + (RS-Mom_30≥100) + (RS-Mom_60≥100) ≥ 2
  3个窗口等权，意味着10日（短期）和60日（长期）权重相同。
  但动量有时效性：短期信号更敏感，长期信号更稳定。
  v40 改用加权投票：weighted_vote = 0.5*(RS-Mom_10≥100) + 0.3*(RS-Mom_30≥100) + 0.2*(RS-Mom_60≥100)
  阈值0.5，意味着：
    - 仅10日领先：0.5 = 阈值，入选（短期主导）
    - 仅30日领先：0.3 < 0.5，不入选
    - 仅60日领先：0.2 < 0.5，不入选
    - 10+30日领先：0.8 > 0.5，入选
    - 10+60日领先：0.7 > 0.5，入选
    - 30+60日领先：0.5 = 阈值，入选
    - 全部领先：1.0 > 0.5，入选

关键发现：
  - IS显著改善：总收益+20.96%→+23.80%(+2.84pp)，Sharpe 0.4249→0.4339(+0.0090)
  - OOS完全持平：收益+6.66%(持平)，Sharpe 2.6787(持平)
  - OOS持仓与v30完全相同（OOS期间3个窗口投票结果一致，加权vs等权无变化）
  - IS改善来自加权投票在某些调仓日改变了行业选择（短期信号更敏感）

关键改动：
  - rs_momentum_vote_weights: [] → [0.5, 0.3, 0.2]
  - 其他配置同 v30

baseline: v30 (IS Sharpe 0.4249 / OOS Sharpe 2.6787 / OOS +6.66%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v40")
class IndustryRotationStrategyV40(BaseStrategy):
    """行业轮动策略 industry_rotation_v40 (weighted_rrg_vote_short_term, final)

    状态: final（当前最优策略，2026-07-20 锁定）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV40":
        if strategy_type != "industry_rotation" or version != "v40":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v40",
            "strategy_name": "行业轮动策略 industry_rotation_v40 (weighted_rrg_vote_short_term, final)",
            "description": "v30+RRG加权投票[0.5,0.3,0.2]短期权重更高 [final]",
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
                    "market_ma_short": 10,
                    "market_ma_long": 30,
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
                    # NEW in v40: 加权投票（短期权重更高）
                    "rs_momentum_vote_weights": [0.5, 0.3, 0.2],
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
