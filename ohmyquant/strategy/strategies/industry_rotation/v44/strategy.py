"""行业轮动策略 v44（基本面因子增强：加入增长因子）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / OOS Sharpe 2.6787 / OOS +6.66%)

v44 = v43 + factor_names 加入 3 个增长因子（等权 1.0）

设计目的：
  v43 当前 12 因子中基本面类只有 LEVEL 指标（gross_income_ratio/roe_ttm/net_profit_ratio），
  缺少 GROWTH 维度。新增 3 个增长因子捕捉"基本面改善"信号：
    - operating_revenue_growth_rate: 营收增长率（顶部增长）
    - net_profit_growth_rate: 净利润增长率（底线增长）
    - np_parent_company_owners_growth_rate: 归母净利润增长率（股东真实增长）

  假设：增长因子与现有 LEVEL 因子正交，能提供独立的选股信号。
  风险：增长因子可能受一次性事件影响（如资产处置），噪声较大。

关键改动：
  - factor_names: 12 → 15（新增 3 个增长因子）
  - factor_weights: 新因子权重 1.0（与现有因子等权）
  - 其他配置同 v43

预期效果：
  - 若增长因子在 IS 期间有效，IS 表现改善
  - OOS 期间市场下跌，增长因子可能无法改变结果（与 v43 持平）
  - 若 IS 改善且 OOS 不损，v44 成为新 FINAL
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v44")
class IndustryRotationStrategyV44(BaseStrategy):
    """行业轮动策略 industry_rotation_v44 (growth_factors, iter)

    状态: iter（v43基础上加入3个增长因子）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV44":
        if strategy_type != "industry_rotation" or version != "v44":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v44",
            "strategy_name": "行业轮动策略 industry_rotation_v44 (growth_factors, iter)",
            "description": "v43+3增长因子(营收/净利润/归母净利润) [iter]",
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
                    # NEW in v44: 12 → 15 因子（新增3增长因子）
                    "factor_names": [
                        "Price1M", "Price3M", "ROC20",
                        "DAVOL10", "money_flow_20",
                        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
                        "earnings_to_price_ratio", "book_to_price_ratio",
                        "raw_beta", "residual_volatility",
                        # NEW in v44: 增长因子（捕捉基本面改善）
                        "operating_revenue_growth_rate",
                        "net_profit_growth_rate",
                        "np_parent_company_owners_growth_rate",
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
                        # NEW in v44: 增长因子等权
                        "operating_revenue_growth_rate": 1.0,
                        "net_profit_growth_rate": 1.0,
                        "np_parent_company_owners_growth_rate": 1.0,
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
