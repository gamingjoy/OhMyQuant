"""行业轮动策略 v41（RRG加权投票权重优化：中期主导）—— [FINAL]

状态: final（当前最优策略，2026-07-20 锁定）
IS Sharpe 0.4803 / OOS Sharpe 2.6787 / OOS 收益 +6.66%（vs 沪深300 -3.01%）
IS显著超越 v40 (IS +27.61% vs +23.80%, Sharpe 0.4803 vs 0.4339)，OOS完全持平

v41 = v40 + rs_momentum_vote_weights: [0.5, 0.3, 0.2] → [0.3, 0.4, 0.3]

设计目的：
  v40 使用短期主导权重 [0.5, 0.3, 0.2]（10日权重最高），基于"短期信号更敏感"假设。
  v41 通过11个权重组合的IS网格搜索发现，中期主导 [0.3, 0.4, 0.3] IS表现最优。

  理论依据：30日动量是"甜蜜点"
    - 10日动量：太短，噪声大，虚假信号多
    - 30日动量：足够长过滤噪声，足够短保持响应
    - 60日动量：太长，滞后性强，反应慢

  v41 中期主导 [0.3, 0.4, 0.3] 的投票行为：
    - 仅10日领先：0.3 < 0.5，不入选（短期信号不足以确认趋势）
    - 仅30日领先：0.4 < 0.5，不入选
    - 仅60日领先：0.3 < 0.5，不入选
    - 10+30日领先：0.7 > 0.5，入选（短中期共振）
    - 10+60日领先：0.6 > 0.5，入选
    - 30+60日领先：0.7 > 0.5，入选（中长期共振，v41新增）
    - 全部领先：1.0 > 0.5，入选

关键发现：
  - IS显著改善：总收益+23.80%→+27.61%(+3.81pp)，Sharpe 0.4339→0.4803(+0.0464)
  - OOS完全持平：收益+6.66%(持平)，Sharpe 2.6787(持平)
  - OOS持仓与v40完全相同（OOS期间3个窗口投票结果一致，权重变化无影响）
  - IS改善来自中期主导权重在某些调仓日改变了行业选择

v41 IS网格搜索完整结果（11个组合，按IS Sharpe降序）：
  [0.3,0.4,0.3] IS +27.61% Sharpe 0.4803 ← v41最优（中期主导）
  [0.6,0.3,0.1] IS +26.02% Sharpe 0.4610（短期主导）
  [0.7,0.2,0.1] IS +26.02% Sharpe 0.4610（短期极端主导）
  [0.4,0.5,0.1] IS +24.53% Sharpe 0.4413
  [0.5,0.3,0.2] IS +23.80% Sharpe 0.4339 ← v40 baseline
  [0.5,0.4,0.1] IS +23.80% Sharpe 0.4339
  [0.6,0.2,0.2] IS +23.86% Sharpe 0.4297
  [0.8,0.1,0.1] IS +23.86% Sharpe 0.4297
  [0.4,0.4,0.2] IS +23.15% Sharpe 0.4226
  [0.4,0.3,0.3] IS +22.78% Sharpe 0.4150
  [0.7,0.3,0.0] IS +21.48% Sharpe 0.4023

关键改动：
  - rs_momentum_vote_weights: [0.5, 0.3, 0.2] → [0.3, 0.4, 0.3]（中期主导）
  - 其他配置同 v40

baseline: v40 (IS Sharpe 0.4339 / OOS Sharpe 2.6787 / OOS +6.66%)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v41")
class IndustryRotationStrategyV41(BaseStrategy):
    """行业轮动策略 industry_rotation_v41 (weighted_rrg_vote_mid_term, final)

    状态: final（当前最优策略，2026-07-20 锁定）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV41":
        if strategy_type != "industry_rotation" or version != "v41":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v41",
            "strategy_name": "行业轮动策略 industry_rotation_v41 (weighted_rrg_vote_mid_term, final)",
            "description": "v40+RRG加权投票权重优化[0.3,0.4,0.3]中期主导 [final]",
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
                    # NEW in v41: 权重优化（中期主导，30日动量甜蜜点）
                    "rs_momentum_vote_weights": [0.3, 0.4, 0.3],
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,
                    "pe_min_industries": 3,
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
