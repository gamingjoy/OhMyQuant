"""行业轮动策略 v49（IC加权替代等权因子）—— [ITER]

状态: iter
baseline: v43 (IS Sharpe 0.5716 / 2024 Sharpe 0.1053 / 2025 Sharpe 2.0319)

v49 = v43 + use_ic_weighting: true + ic_lookback: 60 + ic_horizon: 5

设计目的：
  v45-v48 参数调整均未解决因子时变问题：
    - v45a regime-aware: 2024退化
    - v46 PE回看500: 跨周期恶化
    - v47 PE+PB双估值(ep=0.1+bp=0.1): IS+0.0657但跨周期-0.2157
    - v48 PB权重减半: 2024退化
  结论：参数调整已达瓶颈，需转向结构性改进

  v49 引入IC加权替代等权因子，让因子权重自适应近期表现：
    - 当前: 12因子等权(1.0)，raw_beta=-2.0, residual_volatility=-1.5
    - v49: w_final = sign(w_static) * |mean(rank_IC)|（IC幅度替代静态幅度）
    - IC计算: 滚动60日窗口，前向5日收益的rank IC（Spearman相关）
    - 方向保留: 静态权重的符号（正/负）不变，仅调整幅度

  动机：
    1. 因子时变问题：因子在不同时期有效性不同，等权无法适应
    2. v47 B/P在2024有效但2018-2021反向，IC加权能自动降低失效期权重
    3. 结构性改进：不依赖单一参数调整，从根本上解决因子权重问题

关键改动：
  - use_ic_weighting: false → true
  - ic_lookback: 60（约3个月，平衡稳定性和时效性）
  - ic_horizon: 5（约1周，匹配周频调仓）
  - 其他配置同 v43（保留PE调节RRG投票 alpha=0.2）

预期效果：
  - IS Sharpe 改善（因子权重自适应）
  - 2024 改善（失效因子权重降低）
  - 跨周期稳定（IC加权适应不同市场环境）
  - 若IS+跨周期同时改善，v49成为新FINAL
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v49")
class IndustryRotationStrategyV49(BaseStrategy):
    """行业轮动策略 industry_rotation_v49 (ic_weighting, iter)

    状态: iter（v43基础上引入IC加权替代等权因子）
    """

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV49":
        if strategy_type != "industry_rotation" or version != "v49":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v49",
            "strategy_name": "行业轮动策略 industry_rotation_v49 (ic_weighting, iter)",
            "description": "v43+IC加权替代等权(lookback=60,horizon=5) [iter]",
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
                    # NEW in v49: IC加权替代等权
                    "use_ic_weighting": True,
                    "ic_lookback": 60,
                    "ic_horizon": 5,
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
