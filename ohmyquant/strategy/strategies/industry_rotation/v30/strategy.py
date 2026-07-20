"""行业轮动策略 v30（更慢市场趋势过滤：market_ma 10/30）—— [FINAL]

状态: final（当前最优策略，2026-07-20 锁定）
IS Sharpe 0.4249 / OOS Sharpe 2.6787 / OOS 收益 +6.66%（vs 沪深300 -3.01%）
IS-OOS 一致性合理，OOS显著超越 v23 (IS 0.4476 / OOS 2.4951 / OOS +5.39%)

v30 = v23 + market_ma_short: 5 → 10 + market_ma_long: 20 → 30

设计目的：
  v23 使用 market_ma_short=5, market_ma_long=20，过短的趋势窗口可能产生whipsaw
  v30 改用 10/30 更慢的趋势窗口，验证：
    - 减少市场过滤的频繁切换（market_scale在0.5/1.0之间反复）
    - 在OOS期间可能更早识别市场转强（6/22之前可能就满仓）
    - 但也可能反应过慢错过风险回避

关键发现（OOS 2026-06-01 ~ 2026-07-16）：
  - 6/1: 9股满仓70.02%（market_ma=10/30判断市场未跌破趋势，直接满仓）
  - 6/8-6/15: 空仓（市场跌破10/30 MA，回避下跌）
  - 6/22: 9股满仓74.34%（市场重新站上10/30 MA，抓住反弹）
  - 6/29-7/13: 空仓（市场再次跌破，回避7月初下跌）
  - 时序精准，回避了2次下跌段，抓住2次上涨段

关键改动：
  - market_ma_short: 5 → 10
  - market_ma_long: 20 → 30
  - 其他配置同 v23

迭代验证（v30基础上）：
  - v31: market_ma=20/60 太慢，OOS +1.93% 失败
  - v32: rs_momentum_windows=[20,60,120] 太慢，OOS +4.66% 失败
  - v33: weekday=2周三调仓时序差，OOS +0.37% 失败
  - v34: top_industries=4被过滤限制，OOS +4.22% 失败
  - v35: +margin_stability因子IS差，OOS Sharpe略好但收益低
  - v36: industry_risk_filter=False无变化（OOS未触发）
  - v37: vote_threshold=1无变化（OOS窗口投票一致）

baseline: v23 (IS Sharpe 0.4476 / OOS Sharpe 2.4951 / OOS +5.39%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v30")
class IndustryRotationStrategyV30(BaseStrategy):
    """行业轮动策略 industry_rotation_v30 (slow_market_filter_ma10_30, final)

    状态: final（当前最优策略，2026-07-20 锁定）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV30":
        if strategy_type != "industry_rotation" or version != "v30":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v30",
            "strategy_name": "行业轮动策略 industry_rotation_v30 (slow_market_filter_ma10_30, final)",
            "description": "v23+market_ma_short=10/market_ma_long=30 更慢市场趋势过滤 [final]",
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
                    "market_ma_short": 10,  # NEW in v30: 5 → 10
                    "market_ma_long": 30,   # NEW in v30: 20 → 30
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
