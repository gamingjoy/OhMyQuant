"""ETF 动量轮动策略 v1

在主流 ETF 中按动量排名选 Top-3，月度调仓。
使用 ETFCostModel 计算交易成本。

配置说明：
  - 股票池：8只主流 ETF（沪深300/中证500/创业板/科创50/50ETF/中证1000/光伏/半导体）
  - 因子：动量因子（mom_1m）
  - 选股方法：ICIR
  - 池间分配：等权
  - 风控：波动率目标
  - 调仓频率：月度
  - 成本模型：etf_cn
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.engine.base import BacktestResult

ETF_POOL = [
    "510300.SH",  # 沪深300ETF
    "510500.SH",  # 中证500ETF
    "159915.SZ",  # 创业板ETF
    "588000.SH",  # 科创50ETF
    "510050.SH",  # 50ETF
    "512100.SH",  # 中证1000ETF
    "515790.SH",  # 光伏ETF
    "512480.SH",  # 半导体ETF
    "510880.SH",  # 红利ETF
    "512000.SH",  # 券商ETF
    "159920.SZ",  # 恒生ETF
    "513100.SH",  # 纳指ETF
]


@register_strategy("etf", "v1")
class ETFRotationV1(BaseStrategy):
    """ETF 动量轮动策略 v1"""

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
    ) -> "ETFRotationV1":
        """工厂方法"""
        if strategy_type != "etf" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "etf",
            "strategy_version": "v1",
            "strategy_name": "ETF 动量轮动策略 v1",
            "description": "主流ETF动量轮动策略",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "icir",
                "top_n": 3,
                "max_stock_weight": 0.34,
            },
            "portfolio": {
                "max_stock_weight": 0.34,
            },
            "risk": {
                "target_vol": 0.20,
            },
            "allocation": {
                "method": "equal",
            },
            "rebalance": {
                "frequency": "monthly",
                "method": "cost_benefit",
                "cost_model": {"name": "etf_cn"},
            },
            "factors": ["mom_1m", "mom_3m"],
            "pools": {"main": ETF_POOL},
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
