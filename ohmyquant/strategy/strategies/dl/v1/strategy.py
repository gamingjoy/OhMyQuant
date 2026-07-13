"""DL 选股策略 v1

基于 LSTM 时序模型的选股策略，展示如何将深度学习模型接入回测引擎。

架构:
  - 选股器: ModelSelector (method=model, model_name=lstm)
  - 模型: LSTM（PyTorch），时序特征提取 → 收益预测
  - 特征管线: rank + zscore（截面标准化）
  - 训练: walk-forward，每 21 天重训练
  - 因子: 动量 + 反转 + 技术因子（时序特征丰富）
  - 分配: 等权
  - 风控: 波动率目标
  - 调仓: 月度

依赖:
  pip install torch

配置说明:
  selection.method: model        # 使用 ModelSelector
  selection.model_name: lstm     # 选择 LSTM 模型插件
  selection.model:               # LSTM 超参数
    hidden_dim: 64
    num_layers: 2
    epochs: 30
    batch_size: 256
  selection.ml:                  # 训练管线参数
    train_window: 252            # 训练窗口（1年）
    target_horizon: 20           # 预测 horizon（20日收益）
    retrain_freq: 21             # 重训练频率（月度）
  selection.features:            # 特征变换
    transforms: [rank, zscore]
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

DL_POOL = [
    "600519.SH", "601318.SH", "600036.SH", "000858.SZ", "000333.SZ",
    "600276.SH", "601166.SH", "002594.SZ", "600030.SH", "601888.SH",
    "600050.SH", "601398.SH", "600887.SH", "000651.SZ", "601012.SH",
    "600406.SH", "002415.SZ", "600031.SH", "601628.SH", "000568.SZ",
]


@register_strategy("dl", "v1")
class DLStrategyV1(BaseStrategy):
    """DL 选股策略 v1（LSTM 时序模型）"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "DLStrategyV1":
        if strategy_type != "dl" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "dl",
            "strategy_version": "v1",
            "strategy_name": "DL 选股策略 v1 (LSTM)",
            "description": "基于 LSTM 时序模型的深度学习选股策略",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
                "transaction_cost": 0.001,
            },
            "selection": {
                "method": "model",
                "model_name": "lstm",
                "model": {
                    "hidden_dim": 64,
                    "num_layers": 2,
                    "dropout": 0.2,
                    "epochs": 30,
                    "batch_size": 256,
                    "learning_rate": 0.001,
                    "patience": 10,
                    "device": "auto",
                },
                "ml": {
                    "train_window": 252,
                    "target_horizon": 20,
                    "sample_step": 5,
                    "retrain_freq": 21,
                },
                "features": {
                    "transforms": ["rank", "zscore"],
                },
                "top_n": 10,
                "max_stock_weight": 0.15,
            },
            "portfolio": {
                "max_stock_weight": 0.15,
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
                "mom_6m",
                "rev_5d",
                "rev_20d",
                "vol_20d",
                "vol_60d",
                "rsi_14",
                "bias_20",
            ],
            "pools": {"main": DL_POOL},
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }

        if config:
            base_config.update(config)

        return cls(base_config)
