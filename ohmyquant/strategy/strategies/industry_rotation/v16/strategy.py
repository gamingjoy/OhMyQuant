"""行业轮动策略 v16（多周期RRG + 估值过滤 + 拥挤度动态分域反转）

v16 = v15 + 拥挤度动态分域反转（西南证券思路）

v15 已是当前最优（IS Sharpe 0.4030, OOS +3.32% Sharpe 1.7018）
v16 在 v15 基础上新增西南证券拥挤度动态分域：
  - 非拥挤行业：用动量（趋势跟踪） → 选"赢家"
  - 高拥挤行业：用反转（均值回归） → 选"输家"期望反弹

设计目的：
  v11(拥挤度过滤)直接剔除高拥挤行业，损害表现(Sharpe 0.7666→0.7605)
  v16 改为"保留但切换逻辑"：高拥挤行业不剔除，而是用反转选股
  这样既规避了高拥挤行业的动量崩盘风险，又保留了潜在反弹机会

研报参考：
  - 西南证券《拥挤度动态分域》：非拥挤用动量、高拥挤用反转
  - 实证：高拥挤行业动量效应失效，反转效应显著

实现：
  - 对高拥挤行业(触发数>=2)的股票，反转评分符号(-score)
  - 高拥挤行业选"输家"(低动量)期望反弹
  - 非拥挤行业保持动量(选"赢家")
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v16")
class IndustryRotationStrategyV16(BaseStrategy):
    """行业轮动策略 industry_rotation_v16 (multiperiod_rrg_pe_crowding_rev_csi300, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV16":
        if strategy_type != "industry_rotation" or version != "v16":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v16",
            "strategy_name": "行业轮动策略 industry_rotation_v16 (multiperiod_rrg_pe_crowding_rev_csi300, iter)",
            "description": "多周期RRG+估值过滤+拥挤度动态分域反转+沪深300:12因子+三重防御 [iter]",
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
                    # RRG 多周期投票（同 v14/v15）
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
                    # 拥挤度动态分域反转（NEW in v16, 西南证券思路）
                    # 注意：use_crowding_filter=false（不剔除），use_crowding_reversal=true（反转）
                    "use_crowding_filter": False,
                    "use_crowding_reversal": True,
                    "crowding_window": 250,
                    "crowding_threshold": 0.95,
                    "crowding_min_triggers": 2,
                    "crowding_min_industries": 3,
                    "crowding_factors": [
                        "VOL20", "turnover_volatility", "Skewness20",
                    ],
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
