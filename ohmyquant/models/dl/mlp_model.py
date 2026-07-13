"""MLP 选股模型

多层感知机，用于截面选股打分。需要 PyTorch。
"""
from __future__ import annotations

from ...core.logging import get_logger
from ...core.plugin_system import register_model
from .base_nn import BaseNNModel

logger = get_logger(__name__)

try:
    import torch
    import torch.nn as nn

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:

    class _MLPNet(nn.Module):
        """MLP 网络结构"""

        def __init__(self, input_dim: int, hidden_dims: list[int], dropout: float):
            super().__init__()
            layers = []
            prev = input_dim
            for h in hidden_dims:
                layers.extend([nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)])
                prev = h
            layers.append(nn.Linear(prev, 1))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x)


@register_model("mlp")
class MLPModel(BaseNNModel):
    """MLP 选股模型

    config:
        hidden_dims: [128, 64]
        dropout: 0.2
        epochs: 50
        batch_size: 256
        learning_rate: 0.001
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.hidden_dims = self.config.get("hidden_dims", [128, 64])
        self.dropout = self.config.get("dropout", 0.2)

    def _build_model(self, input_dim: int):
        return _MLPNet(input_dim, self.hidden_dims, self.dropout)


__all__ = ["MLPModel"]
