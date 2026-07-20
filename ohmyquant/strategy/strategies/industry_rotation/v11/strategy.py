"""行业轮动策略 v11（残差动量 + 拥挤度过滤 + 中证500候选池）

B方向：基于华泰金工《行业拥挤度4指标模型》+ 西南证券《拥挤度动态分域》

v11 相对 v10 的改进：
1. 新增拥挤度过滤：
   - 3个指标(VOL20/turnover_volatility/Skewness20)取近250日95%分位
   - >=2个指标触发=高拥挤，剔除该行业
   - 至少保留3个行业（按拥挤度升序补充）
2. 保留v10所有特性：残差动量、中证500候选池、12因子、RRG、绝对动量、大盘过滤

设计思路：
- 残差动量选"真正强势"的行业
- 拥挤度过滤剔除"过度投机"的行业
- 两者互补：残差动量找alpha，拥挤度规避崩盘风险

研报参考：
- 华泰金工《行业拥挤度4指标模型》：4个量价指标95%分位触发，3-4个触发=高拥挤
- 西南证券《拥挤度动态分域》：非拥挤用动量、高拥挤用反转
- 本策略简化为高拥挤直接剔除（不切换到反转）
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v11")
class IndustryRotationStrategyV11(BaseStrategy):
    """行业轮动策略 industry_rotation_v11 (residual_crowding_csi500_rrg220_30, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV11":
        if strategy_type != "industry_rotation" or version != "v11":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v11",
            "strategy_name": "行业轮动策略 industry_rotation_v11 (residual_crowding_csi500_rrg220_30, iter)",
            "description": "残差动量+拥挤度过滤+中证500:12因子+RRG+绝对动量+残差动量+拥挤度3指标95%分位剔除 [iter]",
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
                    "market_index": "000905.XSHG",
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
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    # 残差动量
                    "use_residual_momentum": True,
                    "residual_beta_factor": "raw_beta",
                    "residual_beta_default": 1.0,
                    # 拥挤度过滤（NEW in v11）
                    "use_crowding_filter": True,
                    "crowding_window": 250,
                    "crowding_threshold": 0.95,
                    "crowding_min_triggers": 2,
                    "crowding_min_industries": 3,
                    "crowding_factors": ["VOL20", "turnover_volatility", "Skewness20"],
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
            "pools": {"stocks": {"index": "000905.XSHG"}},
            "data": {
                "source": "duckdb",
                "data_root": "D:/Work/Project/download_a_share/data",
            },
        }

        if config:
            base_config.update(config)

        return cls(base_config)
