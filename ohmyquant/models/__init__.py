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


def _register_builtin_models() -> None:
    """注册内置模型（延迟导入避免依赖问题）"""
    try:
        from .ml.lightgbm_model import LightGBMModel  # noqa: F401
    except ImportError:
        pass
    try:
        from .ml.xgboost_model import XGBoostModel  # noqa: F401
    except ImportError:
        pass
    try:
        from .dl.mlp_model import MLPModel  # noqa: F401
    except ImportError:
        pass
    try:
        from .dl.lstm_model import LSTMModel  # noqa: F401
    except ImportError:
        pass
    try:
        from .rl.portfolio_rl import PortfolioRLModel  # noqa: F401
    except ImportError:
        pass


_register_builtin_models()


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
