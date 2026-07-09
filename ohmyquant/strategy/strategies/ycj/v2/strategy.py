"""YCJ 量化策略 v2

基于 Hybrid 选股器的高级量化策略，使用 ICIR 初筛 + ML 重排 + HRP 分配。

配置说明：
  - 股票池：CSI 800（多池）
  - 因子：动量 + 反转 + 波动率 + 估值
  - 选股方法：Hybrid（ICIR初筛 + ML重排）
  - 池间分配：HRP（层次风险平价）
  - 风控：Regime Adaptive（市场状态自适应）
  - 调仓频率：月度
"""
from __future__ import annotations

from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy import register_strategy
from ohmyquant.engine.base import BacktestResult


@register_strategy("ycj", "v2")
class YCJStrategyV2(BaseStrategy):
    """YCJ 量化策略 v2"""

    def run(self) -> BacktestResult:
        """执行策略"""
        from ...strategy.runner import StrategyRunner

        runner = StrategyRunner(self.config)
        result = runner.run()
        return result.backtest_result

    def get_latest_positions(self) -> dict[str, float]:
        """获取最新持仓"""
        return {}

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "YCJStrategyV2":
        """工厂方法"""
        if strategy_type != "ycj" or version != "v2":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "ycj",
            "strategy_version": "v2",
            "strategy_name": "YCJ 量化策略 v2",
            "description": "基于 Hybrid 选股 + HRP 分配的高级量化策略",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "hybrid",
                "top_n": 100,
                "max_stock_weight": 0.015,
                "min_ic": 0.02,
                "min_ic_ir": 0.1,
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
                "cost_model": {"name": "stock_cn"},
                "cost_benefit_threshold": 0.001,
            },
            "factors": [
                "mom_1m",
                "mom_3m",
                "mom_6m",
                "rev_5d",
                "rev_20d",
                "vol_20d",
                "vol_60d",
            ],
            "pools": {
                "main": [
                    "600519.SH", "601318.SH", "600036.SH", "000858.SZ", "000333.SZ",
                    "600276.SH", "601166.SH", "002594.SZ", "600030.SH", "601888.SH",
                    "600050.SH", "601398.SH", "600887.SH", "000651.SZ", "601012.SH",
                    "600406.SH", "002415.SZ", "600031.SH", "601628.SH", "000568.SZ",
                ]
            },
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
