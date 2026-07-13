"""ML/DL/RL 模型框架

统一的传统/机器学习/深度学习/强化学习模型抽象层。

核心组件:
  - Model: 模型抽象基类
  - FeaturePipeline: 链式特征变换器
  - TrainingPipeline: 训练/推理分离管道
  - WalkForwardRunner: 滚动训练分割器

模型实现:
  - ML: LightGBM (lightgbm_ltr) / XGBoost (xgboost_ltr)
  - DL: MLP (mlp) / LSTM (lstm) — 需 PyTorch
  - RL: PPO Portfolio (ppo_portfolio) — 需 stable-baselines3
"""
from __future__ import annotations

from .base import FeaturePipeline, Model, TrainingPipeline
from .features import (
    BaseTransform,
    IndustryNeutralTransform,
    LagTransform,
    RankTransform,
    WinsorizeTransform,
    ZScoreTransform,
    create_transform,
)
from .walk_forward import WalkForwardRunner

# 导入模型子包以触发自动发现（各子包 __init__ 调用 discover_modules 自扫描）
# 新增模型：在 ml/dl/rl 对应目录下新建 .py + @register_model，无需修改本文件
from . import dl, ml, rl  # noqa: F401


__all__ = [
    "Model",
    "FeaturePipeline",
    "TrainingPipeline",
    "WalkForwardRunner",
    "BaseTransform",
    "RankTransform",
    "ZScoreTransform",
    "WinsorizeTransform",
    "IndustryNeutralTransform",
    "LagTransform",
    "create_transform",
]
