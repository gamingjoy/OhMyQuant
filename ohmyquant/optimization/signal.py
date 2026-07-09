"""信号生成框架

解耦信号生成与选股，支持因子信号、组合信号和模型信号。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


class Signal(ABC):
    """信号抽象基类

    信号是选股的前置步骤，将因子/模型输出转化为 {code: signal_value}。
    选股器可以基于信号进行排序和筛选。
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def generate(
        self,
        data: dict[str, Any],
        idx: int,
        codes: list[str],
    ) -> dict[str, float]:
        """生成信号

        Args:
            data: 数据字典（含因子、行情等）
            idx: 当前时间索引
            codes: 候选标的列表

        Returns:
            {code: signal_value}
        """
        ...


class FactorSignal(Signal):
    """单因子信号

    从因子宽表中提取截面值作为信号。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.factor_name = self.config.get("factor_name", "")

    def generate(self, data: dict[str, Any], idx: int, codes: list[str]) -> dict[str, float]:
        factors = data.get("factors", {})
        if self.factor_name not in factors:
            return {c: 0.0 for c in codes}

        factor_df = factors[self.factor_name]
        if idx >= len(factor_df):
            return {c: 0.0 for c in codes}

        row = factor_df.row(idx, named=True)
        signals: dict[str, float] = {}
        for code in codes:
            v = row.get(code)
            if v is not None and isinstance(v, (int, float)) and not np.isnan(v):
                signals[code] = float(v)
            else:
                signals[code] = 0.0
        return signals


class CompositeSignal(Signal):
    """多因子加权组合信号

    将多个因子信号按权重组合。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.factor_weights: dict[str, float] = self.config.get("factor_weights", {})

    def generate(self, data: dict[str, Any], idx: int, codes: list[str]) -> dict[str, float]:
        if not self.factor_weights:
            return {c: 0.0 for c in codes}

        combined: dict[str, float] = {c: 0.0 for c in codes}
        total_weight = sum(self.factor_weights.values())

        for fname, weight in self.factor_weights.items():
            sub_config = {"factor_name": fname}
            factor_signal = FactorSignal(sub_config)
            signals = factor_signal.generate(data, idx, codes)
            for code in codes:
                combined[code] += signals.get(code, 0.0) * weight / total_weight

        return combined


class ModelSignal(Signal):
    """模型预测信号

    使用 ML/DL/RL 模型生成预测信号。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.model_name = self.config.get("model_name", "lightgbm_ltr")
        self._pipeline = None

    def _ensure_pipeline(self):
        """延迟初始化训练管道"""
        if self._pipeline is not None:
            return
        from ..core.plugin_system import PluginRegistry, PluginType
        from ..models import FeaturePipeline, Model, TrainingPipeline

        model_cfg = self.config.get("model", {})
        model: Model = PluginRegistry.create(
            PluginType.MODEL, self.model_name, config=model_cfg
        )
        features = FeaturePipeline()
        for t in self.config.get("transforms", ["rank", "zscore"]):
            features.add_transform(t)

        pipeline_cfg = self.config.get("pipeline", {})
        self._pipeline = TrainingPipeline(model, features, pipeline_cfg)

    def generate(self, data: dict[str, Any], idx: int, codes: list[str]) -> dict[str, float]:
        self._ensure_pipeline()

        fwd_returns = data.get("fwd_returns")
        factors = data.get("factors", {})

        if fwd_returns is not None:
            self._pipeline.train(factors, fwd_returns, codes, idx)

        result = self._pipeline.predict(factors, codes, idx)
        return result if result is not None else {c: 0.0 for c in codes}


__all__ = [
    "Signal",
    "FactorSignal",
    "CompositeSignal",
    "ModelSignal",
]
