"""RL 组合管理选股器

使用 PPO 强化学习模型直接输出组合权重，不走传统的"选股+分配"流程。
适用于 RL 策略模板，展示如何将 RL 模型接入回测引擎。

配置:
  selection:
    method: rl
    model_name: ppo_portfolio
    model:
      total_timesteps: 10000
      transaction_cost: 0.001
    top_n: 10
    max_stock_weight: 0.2
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import PluginRegistry, PluginType, register_selector
from ..selector import BaseSelector

logger = get_logger(__name__)


@register_selector("rl")
class RLSelector(BaseSelector):
    """RL 组合管理选股器

    使用 PPO 强化学习模型直接输出组合权重。
    在每个调仓日，构建历史收益序列 → 训练/推理 RL 模型 → 输出权重。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.model_name = self.config.get("model_name", "ppo_portfolio")
        self.model_cfg = self.config.get("model", {})
        self._model = None
        self._last_train_idx = -999
        self._retrain_freq = self.config.get("ml", {}).get("retrain_freq", 63)
        self._train_window = self.config.get("ml", {}).get("train_window", 252)

    def _get_or_create_model(self):
        if self._model is None:
            try:
                self._model = PluginRegistry.create(
                    PluginType.MODEL, self.model_name, config=self.model_cfg
                )
            except Exception as e:
                logger.warning(f"创建 RL 模型 {self.model_name} 失败: {e}")
                return None
        return self._model

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        fwd_returns: pl.DataFrame | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        model = self._get_or_create_model()
        if model is None:
            return None

        # 构建历史收益矩阵 (n_days, n_stocks)
        close_numeric = close.drop("date")
        lookback = min(self._train_window, current_idx)
        if lookback < 20:
            return None

        start = max(0, current_idx - lookback)
        recent_close = close_numeric[start : current_idx + 1]
        returns = recent_close / recent_close.shift(1) - 1
        returns = returns.drop_nulls()
        if len(returns) < 10:
            return None

        returns_np = returns.to_numpy()
        # 确保列数与 stock_codes 一致
        available_cols = [c for c in close_numeric.columns if c in stock_codes]
        if len(available_cols) < 2:
            return None

        # 训练 RL 模型（按 retrain_freq 控制）
        need_retrain = (
            not model.fitted
            or (current_idx - self._last_train_idx) >= self._retrain_freq
        )
        if need_retrain:
            env_data = {"returns": returns_np}
            model.config["env_data"] = env_data
            try:
                model.fit()
                self._last_train_idx = current_idx
                logger.debug(f"RL 模型训练完成: {len(returns_np)} timesteps")
            except Exception as e:
                logger.warning(f"RL 模型训练失败: {e}")
                return None

        # 推理：observation = 当前等权权重（与环境 _get_obs 一致）
        obs = np.ones(len(available_cols)) / len(available_cols)

        try:
            weights_raw = model.predict(obs[np.newaxis, :])[0]
        except Exception as e:
            logger.warning(f"RL 推理失败: {e}")
            return None

        # softmax 归一化
        weights_raw = np.clip(weights_raw, 0, 1)
        total = weights_raw.sum()
        if total > 0:
            weights_raw = weights_raw / total
        else:
            weights_raw = np.ones(len(available_cols)) / len(available_cols)

        # 取 top_n
        n = min(self.top_n, len(available_cols))
        top_indices = np.argsort(weights_raw)[-n:]

        weights = {}
        for i in top_indices:
            code = available_cols[i]
            w = float(weights_raw[i])
            if w > 0:
                weights[code] = w

        if not weights:
            return None

        return self.apply_weight_cap(weights)

    def select_strong_factors(self, ic_df: pl.DataFrame, train_end: str) -> list[str]:
        """RL 模式不依赖因子筛选，返回全部因子"""
        return [c for c in ic_df.columns if c != "date"]


__all__ = ["RLSelector"]
