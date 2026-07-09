"""XGBoost 模型

支持 Learning-to-Rank 和回归两种模式。
需要 xgboost 库。
"""
from __future__ import annotations

import numpy as np

from ...core.logging import get_logger
from ...core.plugin_system import register_model
from ..base import Model

logger = get_logger(__name__)

try:
    import xgboost as xgb

    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    logger.info("XGBoost 未安装，xgboost_ltr 模型不可用")


@register_model("xgboost_ltr")
class XGBoostModel(Model):
    """XGBoost Learning-to-Rank 模型

    config:
        n_estimators: 150
        max_depth: 3
        learning_rate: 0.05
        mode: "ranker" / "regressor"
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        if not HAS_XGB:
            raise ImportError("XGBoost 未安装，请运行: pip install xgboost")
        self.n_estimators = self.config.get("n_estimators", 150)
        self.max_depth = self.config.get("max_depth", 3)
        self.learning_rate = self.config.get("learning_rate", 0.05)
        self.mode = self.config.get("mode", "ranker")
        self.model = None

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray | None = None,
        val_data: tuple | None = None,
    ) -> None:
        if self.mode == "ranker":
            self._fit_ranker(X, y, groups, val_data)
        else:
            self._fit_regressor(X, y, val_data)
        self._fitted = True

    def _fit_ranker(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray | None,
        val_data: tuple | None,
    ) -> None:
        dtrain = xgb.DMatrix(X, label=y)
        if groups is not None:
            dtrain.set_group(groups)

        params = {
            "objective": "rank:pairwise",
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbosity": 0,
        }

        evals = []
        if val_data is not None:
            X_val, y_val, g_val = val_data
            dval = xgb.DMatrix(X_val, label=y_val)
            if g_val is not None:
                dval.set_group(g_val)
            evals = [(dtrain, "train"), (dval, "val")]

        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=self.n_estimators,
            evals=evals,
            early_stopping_rounds=20 if evals else None,
            verbose_eval=False,
        )

    def _fit_regressor(self, X: np.ndarray, y: np.ndarray, val_data: tuple | None) -> None:
        dtrain = xgb.DMatrix(X, label=y)
        params = {
            "objective": "reg:squarederror",
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbosity": 0,
        }

        evals = []
        if val_data is not None:
            X_val, y_val, _ = val_data
            dval = xgb.DMatrix(X_val, label=y_val)
            evals = [(dtrain, "train"), (dval, "val")]

        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=self.n_estimators,
            evals=evals,
            early_stopping_rounds=20 if evals else None,
            verbose_eval=False,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted or self.model is None:
            raise RuntimeError("模型未训练")
        dtest = xgb.DMatrix(X)
        return self.model.predict(dtest)

    def save(self, path: str) -> None:
        if self.model is not None:
            self.model.save_model(path)

    def load(self, path: str) -> None:
        self.model = xgb.Booster()
        self.model.load_model(path)
        self._fitted = True


__all__ = ["XGBoostModel"]
