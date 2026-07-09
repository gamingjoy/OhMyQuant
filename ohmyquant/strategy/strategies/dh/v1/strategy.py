"""DH 人工策略 v1

基于规则的人工策略，使用基本面分析 + 技术分析的组合策略。

配置说明：
  - 股票池：自选股池
  - 选股方法：人工精选 + 规则过滤
  - 池间分配：等权
  - 风控：固定仓位
  - 调仓频率：季度
"""
from __future__ import annotations

from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy import register_strategy
from ohmyquant.engine.base import BacktestResult


@register_strategy("dh", "v1")
class DHStrategyV1(BaseStrategy):
    """DH 人工策略 v1"""

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
    ) -> "DHStrategyV1":
        """工厂方法"""
        if strategy_type != "dh" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "dh",
            "strategy_version": "v1",
            "strategy_name": "DH 人工策略 v1",
            "description": "基于规则的人工策略 v1",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "hybrid",
                "top_n": 20,
                "max_stock_weight": 0.05,
            },
            "risk": {
                "target_vol": 0.30,
            },
            "allocation": {
                "method": "equal",
            },
            "rebalance": {
                "frequency": "quarterly",
                "method": "simple",
                "cost_model": {"name": "stock_cn"},
            },
            "factors": ["mom_1m", "mom_3m"],
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
