"""行业轮动策略 v9（RRG 相对强度动量）—— [SUPERSEDED by v15]

状态: superseded（已被 v15 取代，仅作历史参考）
原因: v9 单周期 30日 RS-Mom 存在 data snooping 风险，IS-OOS 一致性差
      v9 IS Sharpe 0.4150 / OOS Sharpe 0.0401（IS 过拟合）
      v15 IS Sharpe 0.4030 / OOS Sharpe 1.7018（IS-OOS 一致，多周期投票+PE过滤）

v8 问题：OOS 收益仍为负（-2.72%），超额仅 +0.29%
         6/22 选了电子/通信/建筑材料，绝对动量（60/120日）仍正但7月下跌
         根因：中长期绝对动量无法识别短期相对强度已转弱的行业

v9 改进（参考 2026 量化轮动策略报告 RRG 框架）：
  - 新增 RRG（Relative Rotation Graph）行业选择层：
    * RS-Ratio = 行业均价/沪深300 的 220 日标准化值（>100 表示长期跑赢大盘）
    * RS-Momentum = RS-Ratio 的 30 日动量（>100 表示相对强度在加速）
    * 行业选择：按 RS-Ratio 取候选，剔除 RS-Momentum<100 的疲软象限
    * RS-Momentum 是先行指标，能在行业还领先时发出转弱预警
  - 30日窗口（vs 研报60日）：能更早识别短期转弱，6/22 OOS能剔除建筑材料(RS-Mom=97.34<100)
  - 保留 v8 所有特性：12因子选股、行业短期风险过滤、绝对动量、大盘过滤

研报参考：
  - 2026 量化轮动策略报告：RRG 框架下行业与ETF轮动策略构建
  - RRG 第一象限策略：年化18.34%, Sharpe 0.72, 最大回撤-29.82%
  - RS-Ratio 回看 220 日为研报最优参数；RS-Mom 30日为本策略适配改进

因子组合:
  动量(3): Price1M, Price3M, ROC20
  成交量(2): DAVOL10, money_flow_20
  质量(3): gross_income_ratio, roe_ttm, net_profit_ratio
  价值(2): earnings_to_price_ratio, book_to_price_ratio
  风险(2): raw_beta(反向,w=-2.0), residual_volatility(反向,w=-1.5)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v9")
class IndustryRotationStrategyV9(BaseStrategy):
    """行业轮动策略 industry_rotation_v9 (mf12_lowbeta_riskfilter20_dualmom20_rrg220_30, superseded)

    状态: superseded by v15 (multiperiod_rrg_pe_csi300)
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV9":
        if strategy_type != "industry_rotation" or version != "v9":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v9",
            "strategy_name": "行业轮动策略 industry_rotation_v9 (mf12_lowbeta_riskfilter20_dualmom20_rrg220_30, iter)",
            "description": "RRG相对强度动量:12因子+行业风险过滤+绝对动量+RRG(RS-Ratio220日+RS-Momentum30日)领先象限+沪深300 [iter]",
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
                    # 行业短期风险过滤：剔除20日内下跌的行业
                    "industry_risk_filter": True,
                    "risk_filter_window": 20,
                    "risk_filter_min_industries": 3,
                    # 绝对动量（Dual Momentum）：20日收益<-3%时仓位×0.5（温和降仓）
                    "absolute_momentum": True,
                    "absolute_momentum_window": 20,
                    "absolute_momentum_threshold": -0.03,
                    "absolute_momentum_scale": 0.5,
                    # 逆波动率加权——经测试损害IS Sharpe，已禁用
                    "use_inv_vol_weight": False,
                    "inv_vol_window": 20,
                    # RRG 框架（NEW in v9）
                    # 30日窗口能在6/22 OOS识别建筑材料短期转弱（RS-Mom=97.34<100）
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,
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
