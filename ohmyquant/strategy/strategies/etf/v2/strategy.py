"""A股+ETF 混合策略 v2

N池架构：A股池（沪深300）+ ETF池（主流ETF），使用混合成本模型。
A股走 StockCostModel，ETF 走 ETFCostModel。

配置说明：
  - 股票池：沪深300成分股 + 8只主流ETF
  - 因子：动量 + 反转 + 波动率
  - 选股方法：Hybrid（ICIR初筛 + ML重排）
  - 池间分配：HRP
  - 风控：Regime Adaptive
  - 调仓频率：月度
  - 成本模型：mixed_cn（自动按标的类型选择）
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

ETF_POOL = [
    "510300.SH",
    "510500.SH",
    "159915.SZ",
    "588000.SH",
    "510050.SH",
    "512100.SH",
    "515790.SH",
    "512480.SH",
]


@register_strategy("etf", "v2")
class ETFMixedV2(BaseStrategy):
    """A股+ETF 混合策略 v2"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "ETFMixedV2":
        """工厂方法"""
        if strategy_type != "etf" or version != "v2":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "etf",
            "strategy_version": "v2",
            "strategy_name": "A股+ETF 混合策略 v2",
            "description": "A股+ETF混合策略，使用混合成本模型",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "hybrid",
                "top_n": 50,
                "max_stock_weight": 0.02,
            },
            "risk": {
                "target_vol": 0.20,
                "vol_trend_mode": "managed_vol",
            },
            "allocation": {
                "method": "hrp",
                "lookback": 60,
            },
            "rebalance": {
                "frequency": "monthly",
                "method": "cost_benefit",
                "cost_model": {"name": "mixed_cn"},
                "cost_benefit_threshold": 0.001,
            },
            "factors": [
                "mom_1m",
                "mom_3m",
                "rev_5d",
                "vol_20d",
            ],
            "pools": {
                "stock_pool": [],
                "etf_pool": ETF_POOL,
            },
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
