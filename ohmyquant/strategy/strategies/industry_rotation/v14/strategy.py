"""行业轮动策略 v14（多周期 RRG 投票）

v9 稳健性分析建议方向：多周期 RRG 组合（10/30/60 日投票），降低单周期过拟合

v9 问题：单周期 RS-Mom(30日) 在 v9 IS 偏好建筑材料，但 v9 OOS 6/22 因 30日 RS-Mom=97.34<100 剔除建筑材料
        单周期参数存在轻度 data snooping 风险，30日 是基于 6/22 OOS 调出的参数

v14 改进：
  - 多周期 RRG 投票：同时计算 10/30/60 日三个 RS-Mom
  - 行业入选需 >=2 个窗口 RS-Mom >= 100（多数投票）
  - 降低单周期过拟合：不再依赖单一窗口的敏感参数
  - 其他参数与 v9 完全一致：12因子+绝对动量+大盘过滤+行业风险过滤+沪深300

设计思路：
  - 10日：短期相对强度（敏感，识别刚转弱）
  - 30日：中期相对强度（v9 使用，识别中期转弱）
  - 60日：长期相对强度（研报推荐，识别长期趋势）
  - 多数投票：>=2 个窗口领先才算领先行业，避免单一窗口噪音

研报参考：
  - 2026 量化轮动策略报告：RS-Ratio(220日)+RS-Momentum(60日)为研报最优
  - v9 稳健性分析：建议多周期 RRG 组合降低单周期过拟合
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v14")
class IndustryRotationStrategyV14(BaseStrategy):
    """行业轮动策略 industry_rotation_v14 (multiperiod_rrg_10_30_60_csi300, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV14":
        if strategy_type != "industry_rotation" or version != "v14":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v14",
            "strategy_name": "行业轮动策略 industry_rotation_v14 (multiperiod_rrg_10_30_60_csi300, iter)",
            "description": "多周期RRG投票(10/30/60日)+沪深300:12因子+三重防御 [iter]",
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
                    # RRG 框架（多周期投票模式 NEW in v14）
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,  # 单周期回退用，多周期模式下不生效
                    # 多周期 RS-Mom 投票
                    "rs_momentum_windows": [10, 30, 60],
                    "rs_momentum_vote_threshold": 2,  # >=2 窗口领先才算领先
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
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
