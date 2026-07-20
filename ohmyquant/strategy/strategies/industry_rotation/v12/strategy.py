"""行业轮动策略 v12（残差动量 + 扩展ML因子库 + 中证500候选池）

C方向：从10因子扩展到40因子，重新尝试LightGBM

v12 相对 v10 的改进：
1. 启用ML选股(use_ml=true)：用LightGBM预测未来20日收益
2. 因子从12个扩展到40个，覆盖8大维度：
   - 动量类(6): Price1M, Price3M, Price1Y, ROC20, ROC60, momentum
   - 成交量类(4): DAVOL10, money_flow_20, single_day_VPT, single_day_VPT_6
   - 波动率类(8): VOL20, VOL60, Variance20/60, sharpe_ratio_20/60, raw_beta, residual_volatility
   - 质量类(5): gross_income_ratio, roe_ttm, roa_ttm, roic_ttm, net_profit_ratio
   - 价值类(3): earnings_to_price_ratio, book_to_price_ratio, cash_flow_to_price_ratio
   - 成长类(5): operating_revenue_growth_rate, net_profit_growth_rate,
              operating_profit_growth_rate, sales_growth, earnings_growth
   - 杠杆类(3): book_leverage, debt_to_asset_ratio, debt_to_equity_ratio
   - Beneish类(6): ACCA, DSRI, GMI, MLEV, LVGI, SGAI (财务造假识别)

设计思路：
- v9 ML实验结论：10因子ML未超越等权线性（因子间非线性关系有限）
- v12假设：扩展到40因子后，ML能捕捉更多非线性关系
- ML参数：150树, 深度3, lr=0.05（抗过拟合配置）
- 训练窗口：252天，重训练频率：21天

参考：
- 之前ML实验结果：ML_v2抗过拟合IS Sharpe 0.1790 < baseline 0.4150
- 本次实验目标：验证扩展因子后ML是否能超越v10的0.7666
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v12")
class IndustryRotationStrategyV12(BaseStrategy):
    """行业轮动策略 industry_rotation_v12 (residual_ml40_csi500_rrg220_30, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV12":
        if strategy_type != "industry_rotation" or version != "v12":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        # 40因子列表
        factor_names_40 = [
            # 动量类(6)
            "Price1M", "Price3M", "Price1Y", "ROC20", "ROC60", "momentum",
            # 成交量类(4)
            "DAVOL10", "money_flow_20", "single_day_VPT", "single_day_VPT_6",
            # 波动率类(8)
            "VOL20", "VOL60", "Variance20", "Variance60",
            "sharpe_ratio_20", "sharpe_ratio_60", "raw_beta", "residual_volatility",
            # 质量类(5)
            "gross_income_ratio", "roe_ttm", "roa_ttm", "roic_ttm", "net_profit_ratio",
            # 价值类(3)
            "earnings_to_price_ratio", "book_to_price_ratio", "cash_flow_to_price_ratio",
            # 成长类(5)
            "operating_revenue_growth_rate", "net_profit_growth_rate",
            "operating_profit_growth_rate", "sales_growth", "earnings_growth",
            # 杠杆类(3)
            "book_leverage", "debt_to_asset_ratio", "debt_to_equity_ratio",
            # Beneish类(6)
            "ACCA", "DSRI", "GMI", "MLEV", "LVGI", "SGAI",
        ]

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v12",
            "strategy_name": "行业轮动策略 industry_rotation_v12 (residual_ml40_csi500_rrg220_30, iter)",
            "description": "残差动量+扩展ML40因子+中证500:残差动量+RRG+绝对动量+LightGBM(40因子,150树) [iter]",
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
                    # 拥挤度过滤（关闭）
                    "use_crowding_filter": False,
                    # ML选股（NEW in v12）
                    "use_ml": True,
                    "ml_train_window": 252,
                    "ml_retrain_freq": 21,
                    "ml_target_horizon": 20,
                    "ml_n_estimators": 150,
                    "ml_max_depth": 3,
                    "ml_learning_rate": 0.05,
                    # 多因子选股（ML失败时回退）
                    "use_factors": True,
                    "factor_names": factor_names_40,
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
