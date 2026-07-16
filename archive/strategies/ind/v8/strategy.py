"""行业轮动策略 v8（ML选股增强+截面z-score+长训练窗口）

v7 问题：ML用原始因子值训练，未做截面标准化，学习绝对水平而非相对排名
v8 改进：
  - 截面 z-score 标准化（每个日期内标准化因子值）
  - 更长训练窗口：252 → 504 天（2年，更多样本）
  - 更多树+更低学习率：150→300树, 0.05→0.03（减少过拟合）
  - 因子集沿用v5的10因子
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("ind", "v8")
class IndRotationStrategyV8(BaseStrategy):
    """行业轮动策略 v8：ML增强 (ml_lgb504_h20_zs_csi300_mkt20)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndRotationStrategyV8":
        if strategy_type != "ind" or version != "v8":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "ind",
            "strategy_version": "v8",
            "strategy_name": "行业轮动策略 v8",
            "description": "ML增强：60+120日行业动量+LightGBM(z-score特征,504天窗口,300树),大盘20日过滤",
            "backtest": {
                "start_date": "2022-01-01",
                "end_date": "2025-12-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "ind",
                "top_n": 10,
                "max_stock_weight": 0.10,
                "ind": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_industries": 5,
                    "stocks_per_industry": 2,
                    "momentum_short": 60,
                    "momentum_long": 120,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,
                    "market_filter": True,
                    "market_index": "000300.XSHG",
                    "market_ma_short": 10,
                    "market_ma_long": 20,
                    "use_ml": True,
                    "use_factors": True,
                    "factor_names": [
                        "Price1M", "Price3M", "ROC20",
                        "DAVOL10", "money_flow_20",
                        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
                        "earnings_to_price_ratio", "book_to_price_ratio",
                    ],
                    "factor_weights": {
                        "Price1M": 1.0, "Price3M": 1.0, "ROC20": 1.0,
                        "DAVOL10": 1.0, "money_flow_20": 1.0,
                        "gross_income_ratio": 1.0, "roe_ttm": 1.0,
                        "net_profit_ratio": 1.0,
                        "earnings_to_price_ratio": 1.0,
                        "book_to_price_ratio": 1.0,
                    },
                    "ml_train_window": 504,
                    "ml_retrain_freq": 21,
                    "ml_target_horizon": 20,
                    "ml_n_estimators": 300,
                    "ml_max_depth": 3,
                    "ml_learning_rate": 0.03,
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
