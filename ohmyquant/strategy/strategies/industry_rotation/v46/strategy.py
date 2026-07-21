"""行业轮动策略 v46（PE回看延长至500天）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)

v46 = v43 + pe_lookback: 250 → 500

设计目的：
  v43 stability 分析显示 2024年(震荡市) PE调节反而有害(Sharpe 0.1053 < v41 0.1826)。
  v45 regime-aware(震荡市关闭PE)尝试失败：2024更差(0.0604)，说明PE在2024震荡期实际有效。
  v45b(alpha_choppy=0.1) = v43完全相同，说明2024的PE调节问题不在alpha大小。

  v46 假设：2024 PE调节失效源于 pe_lookback=250(1年) 过短，导致PE分位不稳定。
    - 1年回看：2024年市场环境变化大，PE分位波动剧烈，可能误判行业估值
    - 2年回看：PE分位更稳定，反映中期估值水平，减少假信号

  预期：
    - 若2024改善 → PE分位不稳定是问题根源，v46为新候选
    - 若2024不变 → PE回看不是问题，需尝试其他方向（PB双估值/IC加权等）

关键改动：
  - pe_lookback: 250 → 500（NEW，PE分位回看窗口延长至2年）
  - 其他配置同 v43
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v46")
class IndustryRotationStrategyV46(BaseStrategy):
    """行业轮动策略 industry_rotation_v46 (pe_lookback_500, iter)

    状态: iter（v43基础上延长PE回看到500天）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV46":
        if strategy_type != "industry_rotation" or version != "v46":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v46",
            "strategy_name": "行业轮动策略 industry_rotation_v46 (pe_lookback_500, iter)",
            "description": "v43+PE回看500天 [iter]",
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
                    # NEW in v46: PE回看延长至500天(2年)
                    "pe_lookback": 500,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
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
