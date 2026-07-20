"""行业轮动策略 v38（独立反转因子修正v16失败实现）—— [ITER]

状态: iter
baseline: v30 (IS Sharpe 0.4249 / OOS Sharpe 2.6787 / OOS +6.66%)

v38 = v30 + use_crowding_filter=true + use_crowding_reversal_factor=true + crowding_reversal_factor=BIAS20

设计目的：
  v16失败根因：对高拥挤行业股票评分取负号(-score)，原评分基于12因子(含质量/价值)，
              取负号相当于选"质量差+估值贵"股票，与原框架冲突，IS Sharpe从0.4030降至0.1908。

  v38正确实现：
    1. 启用拥挤度过滤计算(use_crowding_filter逻辑复用，但不剔除行业)
    2. 对高拥挤行业（≥2个指标触发95%分位）的股票
    3. 用独立反转因子BIAS20单独计算z-score替换原12因子评分
    4. BIAS20低（价格远低于MA20）→ z-score高（反向）→ 选中（期望反弹）
    5. 非拥挤行业保持原12因子评分（动量+质量+价值）

  BIAS20因子方向说明：
    BIAS20 = (close - MA20) / MA20 × 100
    低BIAS20 = 价格远低于20日均线 = 超跌
    crowding_reversal_direction = -1（低值得高分，反转逻辑）

关键改动：
  - use_crowding_filter: false → true（启用拥挤度计算，但crowding_min_triggers高，避免剔除）
  - use_crowding_reversal_factor: false → true（NEW）
  - crowding_reversal_factor: "BIAS20"（NEW）
  - crowding_reversal_direction: -1（NEW，低BIAS20得高分）
  - crowding_min_triggers: 2（保持，>=2触发为高拥挤）
  - crowding_min_industries: 10（提高，避免剔除任何行业，仅用于标记高拥挤）

  注意：use_crowding_filter在v38中不会实际剔除行业（因为crowding_min_industries=10远大于top_industries=3），
       只是为了触发_compute_industry_crowding计算，供use_crowding_reversal_factor使用。

预期效果：
  - 在高拥挤行业切换到反转策略（均值回归）
  - 非拥挤行业保持原动量+质量+价值评分
  - 修正v16的符号反转错误，避免选"质量差+估值贵"股票
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v38")
class IndustryRotationStrategyV38(BaseStrategy):
    """行业轮动策略 industry_rotation_v38 (crowding_reversal_factor_bios20, iter)

    状态: iter（v30基础上修正v16失败实现，使用独立反转因子BIAS20）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV38":
        if strategy_type != "industry_rotation" or version != "v38":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v38",
            "strategy_name": "行业轮动策略 industry_rotation_v38 (crowding_reversal_factor_bios20, iter)",
            "description": "v30+独立反转因子(BIAS20)修正v16失败实现 [iter]",
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
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
                    # NEW in v38: 拥挤度计算（用于标记高拥挤行业，不实际剔除）
                    "use_crowding_filter": True,
                    "crowding_window": 250,
                    "crowding_threshold": 0.95,
                    "crowding_min_triggers": 2,
                    "crowding_min_industries": 10,  # 高于top_industries，避免剔除
                    "crowding_factors": ["VOL20", "turnover_volatility", "Skewness20"],
                    # NEW in v38: 独立反转因子（修正v16失败实现）
                    "use_crowding_reversal_factor": True,
                    "crowding_reversal_factor": "BIAS20",
                    "crowding_reversal_direction": -1,  # 低BIAS20得高分（反转）
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
