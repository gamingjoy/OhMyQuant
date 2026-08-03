"""行业轮动策略 v51（IC符号确认机制）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)

v51 = v50 + ic_sign_confirm: true
      （v50 = v43 + IC乘数模式 scale=0.5 + lookback=120 + horizon=20）

设计目的：
  v50 IC乘数模式结果分析：
    - IS Sharpe 0.5409 (-0.03 vs v43)
    - 2022/2023/2025/2018-2021 全部改善 (+0.04~+0.06)
    - 2024 退化 -0.1870（关键问题）

  v50 失败原因：2024震荡市IC符号频繁翻转，反向IC被错误boost
    - v50 用 |IC| 归一化，不考虑符号
    - 2024年某些因子IC符号与静态权重相反（因子近期失效）
    - 但|IC|仍然较大，导致失效因子被错误boost

  v51 改进：IC符号确认机制
    - 仅当IC符号与静态权重符号一致时，因子才参与boost
    - effective_ic = |IC| if sign(IC)==sign(w_static) else 0
    - norm_ic = effective_ic / max(effective_ic_all)
    - w_final = w_static * (1 + scale * norm_ic)
    - 不一致的因子：w_final = w_static（保持静态，不boost）

  动机：
    1. 正向因子(w>0) + IC>0：因子近期仍有效，boost
    2. 正向因子(w>0) + IC<0：因子近期反向，不boost（保持静态）
    3. 反向因子(w<0) + IC<0：因子近期仍反向有效，boost
    4. 反向因子(w<0) + IC>0：因子近期不再反向，不boost（保持静态）

关键改动（vs v50）：
  - ic_sign_confirm: false → true
  - 其他配置同 v50

预期效果：
  - 2024 改善（反向IC因子不再被boost）
  - 其他年份保持v50的改善（IC符号一致的因子仍boost）
  - 若2024改善且其他年份不退化，v51成为新FINAL
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v51")
class IndustryRotationStrategyV51(BaseStrategy):
    """行业轮动策略 industry_rotation_v51 (ic_sign_confirm, iter)

    状态: iter（v50基础上引入IC符号确认机制）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV51":
        if strategy_type != "industry_rotation" or version != "v51":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v51",
            "strategy_name": "行业轮动策略 industry_rotation_v51 (ic_sign_confirm, iter)",
            "description": "v50+IC符号确认(仅一致时boost) [iter]",
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
                    # NEW in v51: IC符号确认
                    "ic_sign_confirm": True,
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
