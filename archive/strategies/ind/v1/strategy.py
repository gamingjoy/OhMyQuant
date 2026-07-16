"""行业轮动策略 v1（基线版）

基于行业动量的行业轮动策略：
  - 候选池：沪深300成分股
  - 行业分类：申万一级行业
  - 选股逻辑：20日动量(0.6) + 60日动量(0.4) → 行业综合动量
  - 选 Top-5 行业，每行业选 Top-2 只股票（共10只）
  - 单股 ≤ 10%，等权配置
  - 风控：回撤防御（严格控制回撤）
  - 调仓：日频，cost_benefit 调仓器
  - 交易费用：约千分之一（stock_cn 成本模型）

IS 回测：2022-01-01 ~ 2025-12-31
OOS 验证：2026-06-01 ~ 2026-07-15
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("ind", "v1")
class IndRotationStrategyV1(BaseStrategy):
    """行业轮动策略 v1：行业动量基线版 (mom20_60_top5_ind2_csi300)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndRotationStrategyV1":
        if strategy_type != "ind" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "ind",
            "strategy_version": "v1",
            "strategy_name": "行业轮动策略 v1",
            "description": "行业动量基线：20+60日动量,Top5行业×2股,沪深300,日频调仓,回撤防御",
            "backtest": {
                "start_date": "2022-01-01",
                "end_date": "2025-12-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "ind",
                "top_n": 10,
                "max_stock_weight": 0.10,
                "ind": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_industries": 5,
                    "stocks_per_industry": 2,
                    "momentum_short": 20,
                    "momentum_long": 60,
                    "weight_short": 0.6,
                    "weight_long": 0.4,
                    "max_industry_weight": 0.30,
                },
            },
            "portfolio": {
                "max_stock_weight": 0.10,
                "max_industry_weight": 0.30,
                "min_stocks": 5,
            },
            "risk": {
                "method": "drawdown",
                "target_vol": 0.20,
                "lookback": 20,
                "min_exposure_scale": 0.3,
            },
            "rebalance": {
                "frequency": "daily",
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
