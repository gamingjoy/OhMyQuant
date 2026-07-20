"""行业轮动策略 v28（调整绝对动量阈值）—— [ITER]

状态: iter（试验中，2026-07-20）
baseline: v23 (IS Sharpe 0.4476 / OOS Sharpe 2.4951 / OOS +5.39%)

v28 = v23 + absolute_momentum_threshold=-0.05（从-0.03放宽到-0.05）

设计目的：
  v23 的6/1 OOS建仓触发绝对动量降仓(20日收益<-3%仓位×0.5)
  导致6/1-6/8仓位仅35%（一半仓位）
  v28 放宽阈值到-5%，仅在20日收益<-5%时才降仓
  预期6/1仓位提升到70%（不触发降仓），捕获更多6/1-6/8上涨

理论依据：
  - 绝对动量是Antonacci双动量的趋势过滤
  - -3%阈值偏严格，正常市场波动也会触发
  - -5%阈值更宽松，只在显著下跌时降仓
  - 风险：在-3%到-5%区间可能增加损失

v28 改进：
  - absolute_momentum_threshold: -0.03 → -0.05
  - 其他配置同 v23

失败方向回顾：
  - v25 (因子扩展): 失败
  - v26 (逆波动率加权): 失败
  - v27 (target_vol=0.15): 无变化（OOS与v23相同）

baseline: v23 (IS Sharpe 0.4476 / OOS Sharpe 2.4951 / OOS +5.39%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v28")
class IndustryRotationStrategyV28(BaseStrategy):
    """行业轮动策略 industry_rotation_v28 (abs_mom_-0.05, iter)

    状态: iter（试验中，2026-07-20）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV28":
        if strategy_type != "industry_rotation" or version != "v28":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v28",
            "strategy_name": "行业轮动策略 industry_rotation_v28 (abs_mom_-0.05, iter)",
            "description": "v23+absolute_momentum_threshold=-0.05:12因子+沪深300 [iter]",
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
                    "absolute_momentum_threshold": -0.05,  # NEW in v28: -0.03 → -0.05
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
