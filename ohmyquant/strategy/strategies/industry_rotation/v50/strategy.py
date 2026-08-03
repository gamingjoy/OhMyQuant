"""行业轮动策略 v50（IC乘数模式：保留静态权重结构）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)

v50 = v43 + use_ic_weighting: true + ic_weighting_mode: "multiplier"
      + ic_weight_scale: 0.5 + ic_lookback: 120 + ic_horizon: 20

设计目的：
  v49 IC直接替代静态权重完全失败（IS Sharpe 0.5716 → 0.0736）：
    - IC值过小(0.02-0.05)导致所有因子趋近等权
    - 静态权重结构信息丢失(raw_beta -2.0 → -0.03)
    - 5日horizon对价值因子过短

  v50 改进：IC作为静态权重的乘数，保留静态权重结构
    - w_final = w_static * (1 + scale * norm_ic)
    - norm_ic = |IC| / max(|IC|_all_factors) ∈ [0, 1]
    - scale=0.5时：最强因子权重×1.5，最弱因子权重×1.0（保持静态）
    - ic_horizon=20（月频），价值因子需要更长周期体现预测力
    - ic_lookback=120（半年），保证IC估计稳定性

  动机：
    1. 保留v43静态权重结构（raw_beta=-2.0仍是强负权重）
    2. 仅按近期IC幅度调节权重（强IC因子加成，弱IC因子保持）
    3. 避免v49"静态权重信息丢失"问题

关键改动：
  - use_ic_weighting: false → true
  - ic_weighting_mode: "multiplier" (NEW, vs "replacement" for v49)
  - ic_weight_scale: 0.5 (NEW)
  - ic_lookback: 120（vs v49的60，更长更稳定）
  - ic_horizon: 20（vs v49的5，月频更适合价值因子）
  - 其他配置同 v43（保留PE调节RRG投票 alpha=0.2）

预期效果：
  - IS Sharpe 改善（强IC因子权重提升）
  - 2024 改善（失效因子权重不被放大）
  - 跨周期稳定（静态权重结构主导，IC仅做调节）
  - 若IS+2024+跨周期同时改善，v50成为新FINAL
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v50")
class IndustryRotationStrategyV50(BaseStrategy):
    """行业轮动策略 industry_rotation_v50 (ic_multiplier, iter)

    状态: iter（v43基础上引入IC乘数模式，保留静态权重结构）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV50":
        if strategy_type != "industry_rotation" or version != "v50":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v50",
            "strategy_name": "行业轮动策略 industry_rotation_v50 (ic_multiplier, iter)",
            "description": "v43+IC乘数(scale=0.5,lookback=120,horizon=20) [iter]",
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
                    "use_pe_adjusted_rrg_vote": True,
                    "pe_vote_adjust_alpha": 0.2,
                    "use_factors": True,
                    # NEW in v50: IC乘数模式（保留静态权重结构）
                    "use_ic_weighting": True,
                    "ic_weighting_mode": "multiplier",
                    "ic_weight_scale": 0.5,
                    "ic_lookback": 120,
                    "ic_horizon": 20,
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
