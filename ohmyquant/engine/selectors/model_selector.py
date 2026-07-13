"""通用模型选股器

通过 selection.model_name 选择 ML/DL/RL 模型插件，
使用 TrainingPipeline 封装训练/推理流程。

配置:
  selection:
    method: model
    model_name: lightgbm_ltr  # 或 mlp / lstm / ppo_portfolio
    model:
      n_estimators: 150
      max_depth: 3
    top_n: 50
    max_stock_weight: 0.02
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import PluginRegistry, PluginType, register_selector
from ...models import FeaturePipeline, Model, TrainingPipeline
from ..selector import BaseSelector

logger = get_logger(__name__)


@register_selector("model")
class ModelSelector(BaseSelector):
    """通用模型选股器

    使用 TrainingPipeline + Model 插件实现选股。
    支持所有注册的 ML/DL/RL 模型。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.model_name = self.config.get("model_name", "lightgbm_ltr")
        model_cfg = self.config.get("model", {})
        ml_cfg = self.config.get("ml", {})

        pipeline_cfg = {
            "train_window": ml_cfg.get("train_window", 252),
            "target_horizon": ml_cfg.get("target_horizon", 20),
            "sample_step": ml_cfg.get("sample_step", 5),
            "retrain_freq": ml_cfg.get("retrain_freq", 21),
        }

        feature_cfg = self.config.get("features", {})
        self.feature_pipeline = FeaturePipeline()
        transforms = feature_cfg.get("transforms", ["rank", "zscore"])
        if isinstance(transforms, str):
            transforms = [transforms]
        for t in transforms:
            if isinstance(t, str):
                self.feature_pipeline.add_transform(t)
            elif isinstance(t, dict):
                name = t.pop("name")
                self.feature_pipeline.add_transform(name, **t)

        try:
            self.model: Model = PluginRegistry.create(
                PluginType.MODEL, self.model_name, config=model_cfg
            )
        except Exception as e:
            logger.warning(f"创建模型 {self.model_name} 失败: {e}，ML选股不可用")
            self.model = None

        self.pipeline = TrainingPipeline(
            self.model, self.feature_pipeline, pipeline_cfg
        ) if self.model else None

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
        if self.pipeline is None or fwd_returns is None or not strong_factors:
            return None

        self.feature_pipeline._feature_names = [
            f for f in strong_factors if f in factors
        ]
        if not self.feature_pipeline.feature_names:
            return None

        self.pipeline.train(factors, fwd_returns, stock_codes, current_idx)

        scores = self.pipeline.predict(factors, stock_codes, current_idx)
        if scores is None or not scores:
            return None

        score_pairs = [(c, s) for c, s in scores.items() if s == s and s is not None]
        score_pairs.sort(key=lambda x: x[1], reverse=True)
        top = score_pairs[: self.top_n]

        top = [(c, s) for c, s in top if s > 0]
        if not top:
            top = score_pairs[: self.top_n]
            if not top:
                return None

        total = sum(abs(s) for _, s in top)
        if total <= 0:
            n = len(top)
            weights = {c: 1.0 / n for c, _ in top}
        else:
            weights = {c: abs(s) / total for c, s in top}

        return self.apply_weight_cap(weights)


__all__ = ["ModelSelector"]
