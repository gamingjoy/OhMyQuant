"""行业轮动策略 v48（PE+PB双估值调节：PB权重减半）—— [ITER]

状态: iter
baseline: v47 (IS Sharpe 0.6373 / 2024 Sharpe 0.2094 / 2018-2021 Sharpe -0.0540)

v48 = v47 + pe_vote_adjust_alpha: 0.1 → 0.15 + pe_vote_adjust_alpha_pb: 0.1 → 0.05

设计目的：
  v47 PE+PB双估值（各0.1）结果：
    - IS Sharpe +0.0657 (大幅提升) ✓
    - 2024 Sharpe +0.1041 (改善) ✓ 用户关注点达成
    - 2023 Sharpe +0.1388 (显著改善) ✓
    - 2025 Sharpe -0.0067 (持平) ✓
    - 2018-2021 Sharpe -0.2157 (大幅恶化) ✗ 过拟合风险

  v47跨周期恶化提示：B/P信号在2018-2021反向（可能是当时小盘股/周期股行情下B/P失效）
  v48 假设：B/P权重过大是跨周期恶化的主因，减半PB权重应能保留近年改善同时减少跨周期恶化

关键改动：
  - pe_vote_adjust_alpha: 0.1 → 0.15（E/P权重提升，恢复为主信号）
  - pe_vote_adjust_alpha_pb: 0.1 → 0.05（B/P权重减半，作为辅助信号）
  - 总强度保持 0.2（与v43相同），但E/P占75%、B/P占25%

预期效果：
  - IS Sharpe保持改善（仍>0.5716）
  - 2024保持改善（仍>0.1053）
  - 2018-2021恶化减小（绝对值<0.2157，目标接近0.0或正）
  - 若跨周期稳定，v48成为新FINAL
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v48")
class IndustryRotationStrategyV48(BaseStrategy):
    """行业轮动策略 industry_rotation_v48 (pe_pb_reduced_pb, iter)

    状态: iter（v47基础上减半PB权重，平衡跨周期稳定性）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV48":
        if strategy_type != "industry_rotation" or version != "v48":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v48",
            "strategy_name": "行业轮动策略 industry_rotation_v48 (pe_pb_reduced_pb, iter)",
            "description": "v47+PB权重减半(ep=0.15+bp=0.05) [iter]",
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
                    # NEW in v48: E/P权重提升至0.15，B/P权重减半至0.05
                    "pe_vote_adjust_alpha": 0.15,
                    "pe_vote_adjust_alpha_pb": 0.05,
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
