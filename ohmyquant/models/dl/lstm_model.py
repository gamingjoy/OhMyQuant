"""LSTM 时序模型

用于提取时序特征进行选股。需要 PyTorch。
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

    class _LSTMNet(nn.Module):
        """LSTM 网络结构"""

        def __init__(self, input_dim: int, hidden_dim: int, num_layers: int, dropout: float):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0,
            )
            self.fc = nn.Linear(hidden_dim, 1)

        def forward(self, x):
            if x.dim() == 2:
                x = x.unsqueeze(1)
            out, _ = self.lstm(x)
            out = out[:, -1, :]
            return self.fc(out)


@register_model("lstm")
class LSTMModel(BaseNNModel):
    """LSTM 时序选股模型

    config:
        hidden_dim: 64
        num_layers: 2
        dropout: 0.2
        epochs: 50
        batch_size: 256
        learning_rate: 0.001
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.hidden_dim = self.config.get("hidden_dim", 64)
        self.num_layers = self.config.get("num_layers", 2)
        self.dropout = self.config.get("dropout", 0.2)

    def _build_model(self, input_dim: int):
        return _LSTMNet(input_dim, self.hidden_dim, self.num_layers, self.dropout)


__all__ = ["LSTMModel"]
