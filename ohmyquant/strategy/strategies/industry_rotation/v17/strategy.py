"""行业轮动策略 v17（成长+现金流维度扩展）

v17 = v15 + 5个成长/现金流因子（共17个因子）

设计目的：
  v15 的12个因子缺少成长和现金流维度
  成长类因子捕捉公司盈利/营收增长能力
  现金流类因子比会计利润更难操纵，提供更稳健的价值信号
  ROIC 比ROE更全面（剔除财务杠杆影响）

v17 新增5个因子：
  成长类(2):
    - earnings_growth（盈利增长率）
    - operating_revenue_growth_rate（营业收入增长率）
  现金流价值类(2):
    - cash_earnings_to_price_ratio（现金盈利价格比，比E/P更稳健）
    - cash_flow_to_price_ratio（现金流价格比）
  质量扩展(1):
    - roic_ttm（投入资本回报率，比ROE剔除杠杆影响）

研究假设：
  - 成长因子在牛市表现好，现金流因子在熊市防御性强
  - 5个新因子与现有12因子正交，提供独立信号
  - 等权加权，避免过度调参

baseline: v15 (IS Sharpe 0.4030 / OOS Sharpe 1.7018 / OOS +3.32%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v17")
class IndustryRotationStrategyV17(BaseStrategy):
    """行业轮动策略 industry_rotation_v17 (multiperiod_rrg_pe_growth_cashflow_csi300, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV17":
        if strategy_type != "industry_rotation" or version != "v17":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v17",
            "strategy_name": "行业轮动策略 industry_rotation_v17 (multiperiod_rrg_pe_growth_cashflow_csi300, iter)",
            "description": "多周期RRG+PE过滤+成长现金流扩展:17因子(12+5新)+沪深300 [iter]",
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
                    "top_industries": 5,
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
                    # 17 因子 = v15的12 + 新增5（成长2+现金流价值2+质量扩展1）
                    "factor_names": [
                        # v15 原有12因子
                        "Price1M", "Price3M", "ROC20",
                        "DAVOL10", "money_flow_20",
                        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
                        "earnings_to_price_ratio", "book_to_price_ratio",
                        "raw_beta", "residual_volatility",
                        # v17 新增5因子
                        "earnings_growth", "operating_revenue_growth_rate",
                        "cash_earnings_to_price_ratio", "cash_flow_to_price_ratio",
                        "roic_ttm",
                    ],
                    "factor_weights": {
                        # v15 原有12因子权重
                        "Price1M": 1.0, "Price3M": 1.0, "ROC20": 1.0,
                        "DAVOL10": 1.0, "money_flow_20": 1.0,
                        "gross_income_ratio": 1.0, "roe_ttm": 1.0,
                        "net_profit_ratio": 1.0,
                        "earnings_to_price_ratio": 1.0,
                        "book_to_price_ratio": 1.0,
                        "raw_beta": -2.0,
                        "residual_volatility": -1.5,
                        # v17 新增5因子权重（等权1.0）
                        "earnings_growth": 1.0,
                        "operating_revenue_growth_rate": 1.0,
                        "cash_earnings_to_price_ratio": 1.0,
                        "cash_flow_to_price_ratio": 1.0,
                        "roic_ttm": 1.0,
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
