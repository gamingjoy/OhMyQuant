"""行业轮动策略 v52（Regime-aware IC：震荡市禁用IC boost）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)

v52 = v50 + ic_regime_aware: true
      （v50 = v43 + IC乘数模式 scale=0.5 + lookback=120 + horizon=20）

设计目的：
  v50 IC乘数模式结果分析：
    - IS 0.5409(-0.03), 2022/2023/2025/2018-2021 全部改善
    - 2024 退化 -0.1870（关键问题）

  v51 IC符号确认失败：2024更差(-0.1532)，2025也退化(1.9581)
    - IC符号不一致的因子可能含反转信号，强制过滤反而丢失信息

  v52 改进思路：直接针对2024震荡市
    - v50在趋势市(2022/2023/2025)有效，在震荡市(2024)失效
    - 2024是震荡市（market_scale<1.0），IC信号噪声大
    - 解法：震荡市禁用IC boost，回到静态权重（相当于v43）
    - 趋势市保留IC boost，享受v50带来的改善

  实现：
    - market_scale==1.0（趋势市）：使用v50 IC乘数 boost
    - market_scale<1.0（震荡市）：禁用IC boost，w_final=w_static（相当于v43）
    - 这样2024(震荡市)回到v43水平(0.1053)，其他年份保留v50改善

关键改动（vs v50）：
  - ic_regime_aware: false → true
  - 其他配置同 v50（不使用ic_sign_confirm）

预期效果：
  - 2024 回到v43水平（~0.1053，不再退化）
  - 2022/2023/2025 保留v50改善
  - 2018-2021 保留v50改善
  - 若2024回到v43水平且其他年份不退化，v52成为新FINAL
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v52")
class IndustryRotationStrategyV52(BaseStrategy):
    """行业轮动策略 industry_rotation_v52 (regime_aware_ic, iter)

    状态: iter（v50基础上引入regime-aware IC，震荡市禁用IC boost）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV52":
        if strategy_type != "industry_rotation" or version != "v52":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v52",
            "strategy_name": "行业轮动策略 industry_rotation_v52 (regime_aware_ic, iter)",
            "description": "v50+Regime-aware IC(震荡市禁用boost) [iter]",
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
                    # v50 base: IC乘数模式
                    "use_ic_weighting": True,
                    "ic_weighting_mode": "multiplier",
                    "ic_weight_scale": 0.5,
                    "ic_lookback": 120,
                    "ic_horizon": 20,
                    # NEW in v52: Regime-aware IC（震荡市禁用boost）
                    "ic_regime_aware": True,
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
