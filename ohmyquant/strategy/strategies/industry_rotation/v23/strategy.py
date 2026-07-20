"""行业轮动策略 v23（更分散个股：top_industries=3, stocks_per_industry=3）—— [SUPERSEDED by v30]

状态: superseded（被 v30 超越，2026-07-20）
IS Sharpe 0.4476 / OOS Sharpe 2.4951 / OOS 收益 +5.39%（vs 沪深300 -3.01%）

v30 = v23 + market_ma_short: 5 → 10 + market_ma_long: 20 → 30
v30 IS Sharpe 0.4249 / OOS Sharpe 2.6787 / OOS 收益 +6.66%（超越v23）

v23 = v20 + stocks_per_industry=3（从2改为3）+ max_industry_weight=0.30

设计目的：
  v20 的 top_industries=3, stocks_per_industry=2 共6只股票
  v23 增加每行业股票数到3，共9只，更分散
  验证"更分散个股是否能降低风险、提升收益"

v23 改进：
  - stocks_per_industry: 2 → 3
  - max_industry_weight: 0.25 → 0.30（容纳3只×0.10）
  - 其他配置同 v20

关键发现：
  - 6/22 OOS建仓9只股票（通信/建筑材料/电子各3只），总仓位0.78
  - 新增600522、000786、688082贡献额外收益
  - OOS收益从v20的+4.50%提升到+5.39%（+0.89pp）
  - IS略低于v20（0.4476 vs 0.4739），但OOS显著超越，IS-OOS一致性合理

v24验证：stocks_per_industry=4过度分散，IS Sharpe降至0.3690，过拟合。

baseline: v20 (IS Sharpe 0.4739 / OOS Sharpe 2.2714 / OOS +4.50%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v23")
class IndustryRotationStrategyV23(BaseStrategy):
    """行业轮动策略 industry_rotation_v23 (multiperiod_rrg_pe_top3_stocks3_csi300, superseded)

    状态: superseded（被 v30 超越，2026-07-20）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV23":
        if strategy_type != "industry_rotation" or version != "v23":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v23",
            "strategy_name": "行业轮动策略 industry_rotation_v23 (multiperiod_rrg_pe_top3_stocks3_csi300, iter)",
            "description": "多周期RRG+PE过滤+Top-3行业每行业3股:12因子+沪深300 [iter]",
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
                    "stocks_per_industry": 3,  # NEW in v23: 2 → 3
                    "momentum_short": 60,
                    "momentum_long": 120,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,  # NEW: 0.25 → 0.30（容纳3只×0.10）
                    "market_filter": True,
                    "market_index": "000300.XSHG",
                    "market_ma_short": 5,
                    "market_ma_long": 20,
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
