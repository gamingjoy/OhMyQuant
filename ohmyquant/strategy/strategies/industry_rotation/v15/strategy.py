"""行业轮动策略 v15（多周期RRG + 行业估值过滤）

v15 = v14 + 行业估值过滤（华商基金估值安全边际思路）

设计目的：
  华商基金等行业轮动优秀基金公司重视"估值安全边际"
  v14 在 OOS 表现优秀（+3.32%, Sharpe 1.7018），但完全依赖动量+RRG
  加入估值过滤后，可规避"动量虚高+估值泡沫"的行业

v15 改进：
  - 在 v14 基础上新增行业估值过滤层
  - 使用 earnings_to_price_ratio(=1/PE) 作为估值代理
  - E/P 历史分位 < 10%（即 PE 处于近250日90%分位以上）视为过贵，剔除
  - 至少保留 3 个行业（避免全部被剔除）

估值过滤逻辑：
  - 高 E/P = 便宜（低估） → 保留
  - 低 E/P = 昂贵（高估） → 剔除
  - 阈值：E/P 分位 < 0.10（即历史最低10% = 历史最贵10%）

研报参考：
  - 华商基金：行业轮动重视估值安全边际
  - 兴全基金：自下而上+估值锚定
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v15")
class IndustryRotationStrategyV15(BaseStrategy):
    """行业轮动策略 industry_rotation_v15 (multiperiod_rrg_pe_csi300, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV15":
        if strategy_type != "industry_rotation" or version != "v15":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v15",
            "strategy_name": "行业轮动策略 industry_rotation_v15 (multiperiod_rrg_pe_csi300, iter)",
            "description": "多周期RRG+行业估值过滤(E/P分位)+沪深300:12因子+三重防御 [iter]",
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
                    # RRG 多周期投票（同 v14）
                    "use_rrg": True,
                    "rs_ratio_window": 220,
                    "rs_momentum_window": 30,
                    "rs_momentum_windows": [10, 30, 60],
                    "rs_momentum_vote_threshold": 2,
                    "rrg_momentum_threshold": 100.0,
                    "rrg_min_industries": 3,
                    # 行业估值过滤（NEW in v15, 华商基金思路）
                    "use_pe_filter": True,
                    "pe_factor": "earnings_to_price_ratio",
                    "pe_lookback": 250,
                    "pe_expensive_percentile": 0.10,  # E/P 分位<10%视为过贵
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
