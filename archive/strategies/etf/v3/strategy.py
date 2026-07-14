"""ETF 动量轮动策略 v3 (回撤防御)

v1 基础上增加 drawdown 风控管理器：
  - 回撤 >18% → 30% 仓位
  - 回撤 >12% → 45% 仓位
  - 回撤 >8%  → 60% 仓位
  - 崩盘信号（5日收益<-5%）→ 额外降仓
保持 v1 的选股逻辑（ICIR + 12 ETF + top3）确保 alpha 不损失。
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

ETF_POOL_V3 = [
    "510300.SH", "510500.SH", "159915.SZ", "588000.SH", "510050.SH",
    "512100.SH", "515790.SH", "512480.SH", "510880.SH", "512000.SH",
    "159920.SZ", "513100.SH",
]


@register_strategy("etf", "v3")
class ETFRotationV3(BaseStrategy):
    """ETF 动量轮动策略 v3 (回撤防御)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "ETFRotationV3":
        if strategy_type != "etf" or version != "v3":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "etf",
            "strategy_version": "v3",
            "strategy_name": "ETF 动量轮动策略 v3 (回撤防御)",
            "description": "v1+drawdown风控",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.0005,
            },
            "selection": {
                "method": "icir",
                "top_n": 3,
                "max_stock_weight": 0.34,
            },
            "portfolio": {"max_stock_weight": 0.34},
            "risk": {"target_vol": 0.20, "method": "drawdown"},
            "allocation": {"method": "equal"},
            "rebalance": {
                "frequency": "monthly",
                "method": "cost_benefit",
                "cost_model": {"name": "etf_cn"},
            },
            "factors": ["mom_1m", "mom_3m"],
            "pools": {"main": ETF_POOL_V3},
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
