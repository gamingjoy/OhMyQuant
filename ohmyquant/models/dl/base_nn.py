"""PyTorch 神经网络基类

封装训练循环、早停、设备管理。需要 PyTorch（可选依赖）。
"""
from __future__ import annotations

import numpy as np

from ...core.logging import get_logger
from ..base import Model

logger = get_logger(__name__)

try:
    import torch
    import torch.nn as nn

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.info("PyTorch 未安装，DL 模型不可用。请运行: pip install torch")


class BaseNNModel(Model):
    """PyTorch 神经网络基类

    子类需实现 _build_model() 返回 nn.Module。
    config:
        epochs: 50
        batch_size: 256
        learning_rate: 0.001
        patience: 10
        device: "auto" / "cpu" / "cuda"
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        if not HAS_TORCH:
            raise ImportError("PyTorch 未安装，请运行: pip install torch")
        self.epochs = self.config.get("epochs", 50)
        self.batch_size = self.config.get("batch_size", 256)
        self.learning_rate = self.config.get("learning_rate", 0.001)
        self.patience = self.config.get("patience", 10)
        self.device = self._get_device(self.config.get("device", "auto"))
        self.model: nn.Module | None = None

    def _get_device(self, device: str) -> "torch.device":
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(device)

    def _build_model(self, input_dim: int) -> nn.Module:
        """子类实现：构建网络结构"""
        raise NotImplementedError

    def _to_tensor(self, X: np.ndarray, y: np.ndarray | None = None):
        X_t = torch.FloatTensor(X).to(self.device)
        if y is not None:
            y_t = torch.FloatTensor(y).to(self.device)
            return X_t, y_t
        return X_t

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray | None = None,
        val_data: tuple | None = None,
    ) -> None:
        input_dim = X.shape[1]
        self.model = self._build_model(input_dim).to(self.device)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
        criterion = nn.MSELoss()

        X_val, y_val = None, None
        if val_data is not None:
            X_val, y_val, _ = val_data

        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None

        n_samples = len(X)
        for epoch in range(self.epochs):
            self.model.train()
            indices = np.random.permutation(n_samples)
            for start in range(0, n_samples, self.batch_size):
                batch_idx = indices[start : start + self.batch_size]
                X_batch, y_batch = self._to_tensor(X[batch_idx], y[batch_idx])
                optimizer.zero_grad()
                pred = self.model(X_batch).squeeze()
                loss = criterion(pred, y_batch)
                loss.backward()
                optimizer.step()

            if X_val is not None and y_val is not None:
                val_loss = self._eval_loss(X_val, y_val, criterion)
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                else:
                    patience_counter += 1
                    if patience_counter >= self.patience:
                        logger.debug(f"Early stopping at epoch {epoch}")
                        break

        if best_state is not None:
            self.model.load_state_dict(best_state)
        self._fitted = True

    def _eval_loss(self, X: np.ndarray, y: np.ndarray, criterion) -> float:
        self.model.eval()
        with torch.no_grad():
            X_t, y_t = self._to_tensor(X, y)
            pred = self.model(X_t).squeeze()
            return criterion(pred, y_t).item()

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted or self.model is None:
            raise RuntimeError("模型未训练")
        self.model.eval()
        with torch.no_grad():
            X_t = self._to_tensor(X)
            return self.model(X_t).squeeze().cpu().numpy()

    def save(self, path: str) -> None:
        if self.model is not None:
            torch.save(self.model.state_dict(), path)

    def load(self, path: str) -> None:
        if self.model is None:
            input_dim = self.config.get("input_dim", 100)
            self.model = self._build_model(input_dim).to(self.device)
        self.model.load_state_dict(torch.load(path, map_location=self.device))
        self._fitted = True


__all__ = ["BaseNNModel"]
