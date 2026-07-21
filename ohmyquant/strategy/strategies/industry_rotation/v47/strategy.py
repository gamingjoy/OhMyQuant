"""行业轮动策略 v47（PE+PB双估值调节RRG投票）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)

v47 = v43 + pe_vote_adjust_alpha: 0.2 → 0.1 + pe_vote_adjust_alpha_pb: 0.1

设计目的：
  v45 regime-aware尝试：IS+0.0177但2024恶化（PE在震荡市实际有效）
  v46 PE回看500天尝试：IS持平，2024更差，跨周期大幅恶化（失败）
  结论：2024 PE调节失效不是regime问题也不是回看窗口问题，可能是E/P信号本身噪声大

  v47 引入PB+PE双估值调节，提供更稳健的估值信号：
    - E/P (earnings_to_price_ratio): 反映盈利估值，但受盈利波动影响大
    - B/P (book_to_price_ratio): 反映资产估值，更稳定，受一次性损益影响小
    - 双估值加权：adjusted_vote = weighted_vote + 0.1*(ep_pct-0.5) + 0.1*(bp_pct-0.5)
    - 总强度 0.2（与v43相同），但分散到两个正交估值维度

  动机：2024年盈利可能受一次性事件影响（资产减值/汇兑损益），
        导致E/P信号失真；B/P基于账面净资产更稳定，能修正E/P的极端值。

关键改动：
  - pe_vote_adjust_alpha: 0.2 → 0.1（E/P调节强度减半）
  - pe_vote_adjust_alpha_pb: 0.0 → 0.1（NEW，B/P调节强度）
  - 其他配置同 v43

预期效果：
  - 2024改善：B/P稳定信号修正E/P失真
  - 2025不退化：双估值在趋势市同样有效
  - IS整体：双估值更稳健，可能小幅改善
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v47")
class IndustryRotationStrategyV47(BaseStrategy):
    """行业轮动策略 industry_rotation_v47 (pe_pb_dual_adjust, iter)

    状态: iter（v43基础上引入PB+PE双估值调节）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV47":
        if strategy_type != "industry_rotation" or version != "v47":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v47",
            "strategy_name": "行业轮动策略 industry_rotation_v47 (pe_pb_dual_adjust, iter)",
            "description": "v43+PB双估值调节(ep=0.1+bp=0.1) [iter]",
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
                    "rs_momentum_vote_weights": [0.3, 0.4, 0.3],
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
                    "use_pe_adjusted_rrg_vote": True,
                    # NEW in v47: E/P强度减半，新增B/P调节
                    "pe_vote_adjust_alpha": 0.1,
                    "pe_vote_adjust_alpha_pb": 0.1,
                    "pb_factor": "book_to_price_ratio",
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
