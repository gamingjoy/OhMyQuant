"""深度学习模型（PyTorch，可选依赖）"""
from __future__ import annotations

try:
    from .mlp_model import MLPModel
except ImportError:
    pass

try:
    from .lstm_model import LSTMModel
except ImportError:
    pass
