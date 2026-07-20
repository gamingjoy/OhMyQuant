"""行业轮动策略 v42（多周期RRG扩展：5窗口加权投票）—— [ITER]

状态: iter
baseline: v41 (IS Sharpe 0.4803 / OOS Sharpe 2.6787 / OOS +6.66%)

v42 = v41 + rs_momentum_windows: [10, 30, 60] → [5, 10, 20, 30, 60]
            + rs_momentum_vote_weights: [0.3, 0.4, 0.3] → [0.1, 0.2, 0.3, 0.3, 0.1]

设计目的：
  v41 使用 3 窗口 [10, 30, 60] 加权投票，v42 扩展到 5 窗口 [5, 10, 20, 30, 60]。
  更多窗口能更精细捕捉不同周期的动量信号，降低单周期过拟合风险。

  权重设计 [0.1, 0.2, 0.3, 0.3, 0.1]（中期主导）：
    - 5日:  0.1 (太短噪声大，虚假信号多)
    - 10日: 0.2 (短周期，权重适中)
    - 20日: 0.3 (中周期，权重较高)
    - 30日: 0.3 (甜蜜点，权重最高)
    - 60日: 0.1 (太长滞后，权重低)

  v42 5 窗口加权投票行为：
    - 仅5日领先: 0.1 < 0.5，不入选
    - 5+10日领先: 0.3 < 0.5，不入选
    - 5+10+20日领先: 0.6 > 0.5，入选（短中期共振）
    - 20+30日领先: 0.6 > 0.5，入选（中期共振）
    - 30+60日领先: 0.4 < 0.5，不入选（中长期共振不足）
    - 全部领先: 1.0 > 0.5，入选

关键改动：
  - rs_momentum_windows: [10, 30, 60] → [5, 10, 20, 30, 60]
  - rs_momentum_vote_weights: [0.3, 0.4, 0.3] → [0.1, 0.2, 0.3, 0.3, 0.1]
  - 其他配置同 v41

预期效果：
  - 5 窗口能更精细捕捉动量信号
  - 中期主导权重符合 30 日动量甜蜜点理论
  - 可能降低单周期过拟合，提升 IS-OOS 一致性
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v42")
class IndustryRotationStrategyV42(BaseStrategy):
    """行业轮动策略 industry_rotation_v42 (5window_rrg_vote_mid_term, iter)

    状态: iter（v41基础上扩展到5窗口加权投票）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV42":
        if strategy_type != "industry_rotation" or version != "v42":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v42",
            "strategy_name": "行业轮动策略 industry_rotation_v42 (5window_rrg_vote_mid_term, iter)",
            "description": "v41+5窗口RRG[5,10,20,30,60]加权[0.1,0.2,0.3,0.3,0.1] [iter]",
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
                    # NEW in v42: 5窗口扩展
                    "rs_momentum_windows": [5, 10, 20, 30, 60],
                    "rs_momentum_vote_threshold": 2,
                    # NEW in v42: 5窗口权重（中期主导）
                    "rs_momentum_vote_weights": [0.1, 0.2, 0.3, 0.3, 0.1],
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
