"""RL 组合管理策略 v1

基于 PPO 强化学习的组合权重优化策略，展示如何将 RL 模型接入回测引擎。

架构:
  - 选股器: RLSelector (method=rl)
  - 模型: PPO Portfolio（stable-baselines3），直接输出组合权重
  - 训练: 在线 walk-forward，每 63 天重训练
  - 因子: 动量 + 反转 + 波动率（用于环境特征）
  - 分配: RL 模型直接输出权重，不使用额外分配器
  - 风控: 波动率目标
  - 调仓: 月度

依赖:
  pip install stable-baselines3 gymnasium

与 ML/DL 策略的区别:
  - ML/DL: 模型输出每只股票的得分 → 排名选股 → 分配权重
  - RL: 模型直接输出组合权重（end-to-end 优化）

配置说明:
  selection.method: rl             # 使用 RLSelector
  selection.model_name: ppo_portfolio  # PPO 组合管理模型
  selection.model:
    total_timesteps: 10000         # PPO 训练步数
    transaction_cost: 0.001        # 环境中的交易成本
  selection.ml:
    train_window: 252              # 历史数据窗口
    retrain_freq: 63               # 重训练频率（季度）
"""
from __future__ import annotations

from ohmyquant.engine.base import BacktestResult
from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

RL_POOL = [
    "600519.SH", "601318.SH", "600036.SH", "000858.SZ", "000333.SZ",
    "600276.SH", "601166.SH", "002594.SZ", "600030.SH", "601888.SH",
    "600050.SH", "601398.SH", "600887.SH", "000651.SZ", "601012.SH",
    "600406.SH", "002415.SZ", "600031.SH", "601628.SH", "000568.SZ",
]


@register_strategy("rl", "v1")
class RLStrategyV1(BaseStrategy):
    """RL 组合管理策略 v1（PPO）"""

    def run(self) -> BacktestResult:
        from ...strategy.runner import StrategyRunner

        runner = StrategyRunner(self.config)
        result = runner.run()
        return result.backtest_result

    def get_latest_positions(self) -> dict[str, float]:
        return {}

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "RLStrategyV1":
        if strategy_type != "rl" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "rl",
            "strategy_version": "v1",
            "strategy_name": "RL 组合管理策略 v1 (PPO)",
            "description": "基于 PPO 强化学习的组合权重优化策略",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "rl",
                "model_name": "ppo_portfolio",
                "model": {
                    "total_timesteps": 10000,
                    "transaction_cost": 0.001,
                    "learning_rate": 0.0003,
                    "n_steps": 2048,
                    "batch_size": 64,
                },
                "ml": {
                    "train_window": 252,
                    "retrain_freq": 63,
                },
                "top_n": 10,
                "max_stock_weight": 0.2,
            },
            "portfolio": {
                "max_stock_weight": 0.2,
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
                "cost_model": {"name": "stock_cn"},
                "cost_benefit_threshold": 0.002,
            },
            "factors": [
                "mom_1m",
                "mom_3m",
                "rev_20d",
                "vol_20d",
                "vol_60d",
            ],
            "pools": {"main": RL_POOL},
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
