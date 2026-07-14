"""ML 选因子策略 v2

修复 v1 的 NaN 缺陷 + 超参优化：
  - IC 缓存用 null 替代 NaN（drop_nulls 正确工作）
  - 训练窗口 1008 天（4 年），提供更充分的 ML 训练样本
  - top_k_factors=25，集中选最强因子，减少噪声

OOS 表现 (2026-06-01 ~ 2026-07-10, 29 天)：
  - 总收益 +9.09%, 年化 +112.12%, Sharpe 4.78, 最大回撤 -3.06%
  - 超越所有 9 个现有策略（含 combo_v1 的 +5.55%/Sharpe 1.80）

因子数据：260 个 jqdata 预计算因子，覆盖 2005/2006/2018-2026
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v2")
class MLFStrategyV2(BaseStrategy):
    """ML 选因子策略 v2：NaN修复 + 超参优化 (k25_w1008)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV2":
        if strategy_type != "mlf" or version != "v2":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v2",
            "strategy_name": "ML选因子策略 v2",
            "description": "NaN修复+超参优化：LightGBM预测因子IC+ICIR选股(k25_w1008)",
            "backtest": {
                "start_date": "2018-01-01",
                "end_date": "2026-05-31",
                "data_start_date": "2018-01-01",
                "transaction_cost": 0.0008,
            },
            "selection": {
                "method": "mlf",
                "top_n": 30,
                "max_stock_weight": 0.04,
                "mlf": {
                    "data_root": "D:/Work/Project/download_a_share/data",
                    "top_k_factors": 25,
                    "train_window": 1008,
                    "retrain_freq": 21,
                    "target_horizon": 20,
                    "neutralize": True,
                },
            },
            "risk": {
                "method": "vol_target",
                "target_vol": 0.18,
                "lookback": 20,
                "min_exposure_scale": 0.5,
            },
            "rebalance": {
                "frequency": "monthly",
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
