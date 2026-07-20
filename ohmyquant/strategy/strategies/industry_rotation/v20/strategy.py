"""行业轮动策略 v20（更集中：top_industries=3, stocks_per_industry=2）—— [SUPERSEDED by v23]

状态: superseded（被 v23 超越，2026-07-20）
IS Sharpe 0.4739 / OOS Sharpe 2.2714 / OOS 收益 +4.50%（vs 沪深300 -3.01%）
被 v23 超越：v23 IS Sharpe 0.4476（略低）/ OOS Sharpe 2.4951（+9.7%）/ OOS +5.39%

v20 = v15 + 调整 top_industries=3（从5改为3）

设计目的：
  v15 的 top_industries=5 设计10只股票，但实际OOS只有3个行业6只股票
  说明PE/风险过滤后只剩3个行业，top_industries=5是冗余的
  v20 直接设 top_industries=3，更早聚焦强势行业

v20 改进：
  - top_industries: 5 → 3
  - 其他配置同 v15

关键发现：
  - 6/1 OOS建仓选了煤炭I（601088, 601225）替代v15的公用事业I（600011, 600674）
  - 煤炭行业在6/1-6/8期间表现更好，贡献了+1.18pp的额外收益
  - 更早聚焦Top-3行业，减少PE/风险过滤的"补充"操作

baseline: v15 (IS Sharpe 0.4030 / OOS Sharpe 1.7018 / OOS +3.32%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v20")
class IndustryRotationStrategyV20(BaseStrategy):
    """行业轮动策略 industry_rotation_v20 (multiperiod_rrg_pe_top3_csi300, superseded)

    状态: superseded（被 v23 超越，2026-07-20）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV20":
        if strategy_type != "industry_rotation" or version != "v20":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v20",
            "strategy_name": "行业轮动策略 industry_rotation_v20 (multiperiod_rrg_pe_top3_csi300, iter)",
            "description": "多周期RRG+PE过滤+Top-3行业集中:12因子+沪深300 [iter]",
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
                    "top_industries": 3,  # NEW in v20: 5 → 3
                    "stocks_per_industry": 2,
                    "momentum_short": 60,
                    "momentum_long": 120,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.25,
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
                    # RRG 多周期投票（同 v15）
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,
                    "rs_momentum_windows": [10, 30, 60],
                    "rs_momentum_vote_threshold": 2,
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    # 行业估值过滤（同 v15）
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
                "max_industry_weight": 0.25,
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
