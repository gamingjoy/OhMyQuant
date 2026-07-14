"""ML 选因子策略 v1

两阶段机器学习选因子：
  Stage 1: LightGBM 预测 260 个预计算因子下月 IC → 选 top-30 因子
  Stage 2: ICIR 加权在选定因子上选 30 只股票

融入 2026 H1 研报创新点：
  - 因子拥挤度特征 (华泰 2026-03)
  - 市场状态条件特征 (MRA-AGRU 2026-03)
  - 收益截面中性化 (国海金工 2026-05)

因子数据：260 个 jqdata 预计算因子，覆盖 2005/2006/2018-2026
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("mlf", "v1")
class MLFStrategyV1(BaseStrategy):
    """ML 选因子策略 v1：两阶段 ML 选因子 + ICIR 选股"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MLFStrategyV1":
        if strategy_type != "mlf" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v1",
            "strategy_name": "ML选因子策略 v1",
            "description": "两阶段ML选因子：LightGBM预测因子IC+ICIR选股",
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
                    "top_k_factors": 30,
                    "train_window": 756,
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
