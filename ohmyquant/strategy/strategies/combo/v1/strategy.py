"""综合策略 v1

8 策略思路综合：
  - 沪深300 大池 + ETF 多池（ycj_v1 的股票池 + etf_v2 的 ETF 分散）
  - 多因子：动量 + 反转 + 波动率（ycj_v1 的动量 + dl_v1 的因子多样性）
  - ICIR 选股，top_n=30（平衡 ycj_v1 的 50 只分散与 dl_v1 的 10 只集中）
  - vol_target 风控（避免 etf_v3 的 drawdown 风控反向放大）
  - icir_weighted 池间分配（根据近期 ICIR 动态调整股票/ETF 权重）
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

ETF_POOL = [
    "510300.SH", "510500.SH", "159915.SZ", "588000.SH",
    "510050.SH", "512100.SH", "510880.SH", "512000.SH",
]


@register_strategy("combo", "v1")
class ComboStrategyV1(BaseStrategy):
    """综合策略 v1：多池 + 多因子 + ICIR 选股 + 波动率目标风控"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "ComboStrategyV1":
        if strategy_type != "combo" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "combo",
            "strategy_version": "v1",
            "strategy_name": "综合策略 v1",
            "description": "8策略综合：多池+多因子+ICIR+vol_target",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.0008,
            },
            "selection": {
                "method": "icir",
                "top_n": 30,
                "max_stock_weight": 0.04,
                "icir_window": 60,
                "icir_floor": 0.3,
            },
            "risk": {
                "method": "vol_target",
                "target_vol": 0.18,
                "lookback": 20,
                "min_exposure_scale": 0.5,
            },
            "allocation": {
                "method": "icir_weighted",
                "lookback": 20,
            },
            "rebalance": {
                "frequency": "monthly",
                "method": "cost_benefit",
                "cost_model": {"name": "stock_cn"},
            },
            "factors": ["mom_1m", "mom_3m", "rev_5d", "vol_20d", "vol_60d"],
            "pools": {
                "stocks": {"index": "000300.XSHG"},
                "etfs": ETF_POOL,
            },
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
