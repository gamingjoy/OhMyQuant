"""行业轮动策略 v43（PE分位作为RRG投票权重调节因子）—— [FINAL]

状态: final（当前最优策略，2026-07-20 锁定）
IS Sharpe 0.5716 / OOS Sharpe 2.6787 / OOS 收益 +6.66%（vs 沪深300 -3.01%）
IS显著超越 v41 (IS +31.29% vs +27.61%, Sharpe 0.5716 vs 0.4803)，OOS完全持平

v43 = v41 + use_pe_adjusted_rrg_vote: true + pe_vote_adjust_alpha: 0.2

设计目的：
  v41 RRG加权投票只考虑动量信号（10/30/60日RS-Mom≥100加权），未考虑估值维度。
  v15 PE过滤（硬性剔除）在OOS未触发（market_filter+RRG已规避估值泡沫行业）。
  v43 引入PE调节RRG投票（软性调节），让估值便宜的行业在投票中加分，估值贵的行业减分。

  v43 PE调节公式：
    adjusted_vote = weighted_vote + alpha * (ep_percentile - 0.5)
    - ep_percentile=1（最便宜）：vote + 0.5*alpha（加分，更易入选）
    - ep_percentile=0.5（中位）：vote + 0（不变）
    - ep_percentile=0（最贵）：vote - 0.5*alpha（减分，更难入选）

  alpha=0.2 表示最大±0.1的调节，相对原阈值0.5是20%的调节幅度。
  与use_pe_filter（硬性剔除）互补：pe_filter是硬性剔除，pe_adjusted_rrg_vote是软性调节。

关键发现：
  - IS显著改善：总收益+27.61%→+31.29%(+3.68pp)，Sharpe 0.4803→0.5716(+0.0913, +19%)
  - OOS完全持平：收益+6.66%(持平)，Sharpe 2.6787(持平)
  - OOS持仓与v41完全相同（PE调节幅度±0.1不足以改变OOS投票结果）
  - IS改善来自PE调节在IS震荡市投票分歧时改变了行业选择

关键改动：
  - use_pe_adjusted_rrg_vote: false → true（NEW）
  - pe_vote_adjust_alpha: 0.2（NEW，PE调节强度）
  - 其他配置同 v41

baseline: v41 (IS Sharpe 0.4803 / OOS Sharpe 2.6787 / OOS +6.66%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v43")
class IndustryRotationStrategyV43(BaseStrategy):
    """行业轮动策略 industry_rotation_v43 (pe_adjusted_rrg_vote, final)

    状态: final（当前最优策略，2026-07-20 锁定）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV43":
        if strategy_type != "industry_rotation" or version != "v43":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v43",
            "strategy_name": "行业轮动策略 industry_rotation_v43 (pe_adjusted_rrg_vote, final)",
            "description": "v41+PE调节RRG投票(alpha=0.2) [final]",
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
                    "rs_momentum_vote_weights": [0.3, 0.4, 0.3],
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
                    # NEW in v43: PE调节RRG投票
                    "use_pe_adjusted_rrg_vote": True,
                    "pe_vote_adjust_alpha": 0.2,
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
