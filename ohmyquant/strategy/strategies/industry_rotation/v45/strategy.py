"""行业轮动策略 v45（regime-aware PE调节RRG投票）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / OOS Sharpe 2.6787 / OOS +6.66%)

v45 = v43 + pe_vote_adjust_alpha_choppy: 0.0（震荡市关闭PE调节）

设计目的：
  v43 stability 分析显示 PE调节存在 regime 依赖：
    - 2024年(震荡市): v43 Sharpe 0.1053 < v41 0.1826 → PE调节在震荡市反而有害（value trap）
    - 2025年(趋势市): v43 Sharpe 2.0319 > v41 1.6716 → PE调节在趋势市有效
    - 2022年(下跌市): v43 Sharpe -0.4202 > v41 -0.5856 → PE调节在下跌市略好
    - 2023年(震荡市): v43 Sharpe 0.1077 > v41 0.0670 → PE调节略好

  v45 引入 regime-aware PE调节：
    - 趋势市(market_scale>=1.0, 沪深300>短MA>长MA): alpha=0.2（保留v43强度）
    - 震荡市(market_scale<1.0, 沪深300<短MA 或 绝对动量为负): alpha=0.0（关闭PE调节，纯动量）

  动机：震荡市中"便宜"行业常是 value trap（便宜还可能更便宜），
        PE调节会让策略偏向低估行业但错过动量行业；
        趋势市中估值便宜的行业更可能有 mean reversion 的alpha。

关键改动：
  - pe_vote_adjust_alpha_choppy: 0.0（NEW，震荡市PE调节强度）
  - 其他配置同 v43

预期效果：
  - 2024年(震荡市)表现改善（关闭PE调节，回到v41水平或更好）
  - 2025年(趋势市)表现保持（PE调节仍生效）
  - IS整体Sharpe可能略降（因为2025贡献了大部分alpha），但近两年稳定性提升
  - 若IS Sharpe不显著下降且2024改善，v45成为新候选
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v45")
class IndustryRotationStrategyV45(BaseStrategy):
    """行业轮动策略 industry_rotation_v45 (regime_aware_pe_adjust, iter)

    状态: iter（v43基础上引入震荡市PE调节关闭）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV45":
        if strategy_type != "industry_rotation" or version != "v45":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v45",
            "strategy_name": "行业轮动策略 industry_rotation_v45 (regime_aware_pe_adjust, iter)",
            "description": "v43+震荡市关闭PE调节(alpha_choppy=0.0) [iter]",
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
                    # NEW in v45: 震荡市PE调节强度（regime-aware）
                    "pe_vote_adjust_alpha_choppy": 0.0,
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
