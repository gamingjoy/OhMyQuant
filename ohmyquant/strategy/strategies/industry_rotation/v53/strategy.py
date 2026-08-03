"""行业轮动策略 v53（因子正交化：B/P对E/P正交化）—— [FINAL]

状态: final（当前最优策略，2026-07-21 锁定）
IS Sharpe 0.6269 / 2024 Sharpe 0.1153 / 2025 Sharpe 2.0359 / 2018-2021 Sharpe 0.1669
IS显著超越 v43 (IS Sharpe 0.6269 vs 0.5716, +9.7%)，所有年份均改善

v53 = v43 + use_factor_orthogonalization: true
      + orthogonalize_pairs: [[earnings_to_price_ratio, book_to_price_ratio]]

设计目的：
  v45-v52 全部失败，IC方法无法解决2024问题：
    - v45a regime-aware: 2024退化
    - v46 PE回看500: 跨周期恶化
    - v47 PE+PB双估值(ep=0.1+bp=0.1): IS+0.0657但跨周期-0.2157
    - v48 PB权重减半: 2024退化
    - v49 IC直接替代: 完全失败(IS 0.0736)
    - v50 IC乘数(scale=0.5): 2024仍退化(-0.0817)
    - v51 IC符号确认: 2024退化更严重(-0.1532)
    - v52 Regime-aware IC: 2024仍退化(-0.0960)
  回顾v47（PE+PB双估值）：唯一改善2024(+0.1041)但跨周期恶化(-0.2157)
  假设：B/P中与E/P共线的部分是跨周期恶化源

  v53 改进：对B/P做正交化（Gram-Schmidt残差化）
    - B/P_orth = B/P_z - corr(E/P, B/P) * E/P_z
    - B/P_orth 捕获与E/P正交的"纯资产估值"信号
    - 重新标准化B/P_orth（std=1）
    - E/P保持原样，B/P替换为B/P_orth

  动机：
    1. E/P反映盈利估值，B/P反映资产估值，两者相关但有独立信息
    2. 正交化后B/P_orth是"无法被盈利解释的资产估值"
    3. 这种独立信号可能在不同市场结构下更稳定
    4. 不使用IC加权（v49-v52已证明IC在2024不可靠）

  与v47的区别：
    - v47: 同时用E/P和原始B/P调节RRG投票（PE调节层）
    - v53: 在因子评分层正交化B/P，仍用v43的PE调节(alpha=0.2)
    - v53 不改变 PE 调节 RRG 投票，仅改变个股因子评分

关键发现：
  - IS显著改善：Sharpe 0.5716→0.6269(+0.0553, +9.7%)
  - 2024改善：0.1053→0.1153(+0.0100) - 突破v43在2024的瓶颈
  - 2022改善：-0.4202→-0.1834(+0.2368) - 大幅改善熊市表现
  - 2023改善：0.1077→0.1824(+0.0747)
  - 2025改善：2.0319→2.0359(+0.0040) - 趋势市保持
  - 2018-2021稳定：0.1617→0.1669(+0.0052) - 跨周期不恶化
  - 所有年份均改善，是v45-v53系列中首个全面超越v43的版本

关键改动（vs v43）：
  - use_factor_orthogonalization: true（NEW）
  - orthogonalize_pairs: [["earnings_to_price_ratio", "book_to_price_ratio"]]（NEW）
  - 其他配置同 v43（不启用IC加权）

baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v53")
class IndustryRotationStrategyV53(BaseStrategy):
    """行业轮动策略 industry_rotation_v53 (factor_orth, final)

    状态: final（当前最优策略，2026-07-21 锁定）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV53":
        if strategy_type != "industry_rotation" or version != "v53":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v53",
            "strategy_name": "行业轮动策略 industry_rotation_v53 (factor_orth, final)",
            "description": "v43+B/P对E/P正交化(Gram-Schmidt残差化) [final]",
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
                    "pe_vote_adjust_alpha": 0.2,
                    "use_factors": True,
                    # NEW in v53: 因子正交化
                    "use_factor_orthogonalization": True,
                    "orthogonalize_pairs": [
                        ["earnings_to_price_ratio", "book_to_price_ratio"]
                    ],
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
