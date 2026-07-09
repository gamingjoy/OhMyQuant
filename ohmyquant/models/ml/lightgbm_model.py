"""LightGBM 模型

支持 Learning-to-Rank (LGBMRanker) 和回归 (LGBMRegressor) 两种模式。
迁移自 engine/selectors/ml_selector.py 的训练逻辑。
"""
from __future__ import annotations

import numpy as np

from ...core.logging import get_logger
from ...core.plugin_system import register_model
from ..base import Model

logger = get_logger(__name__)

try:
    import lightgbm as lgb

    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    logger.info("LightGBM 未安装，lightgbm_ltr 模型不可用")


@register_model("lightgbm_ltr")
class LightGBMModel(Model):
    """LightGBM Learning-to-Rank 模型

    config:
        n_estimators: 150
        max_depth: 3
        learning_rate: 0.05
        mode: "ranker" / "regressor"
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        if not HAS_LGB:
            raise ImportError("LightGBM 未安装，请运行: pip install lightgbm")
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
        self.model = lgb.LGBMRanker(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=0.8,
            colsample_bytree=0.8,
            verbose=-1,
            n_jobs=-1,
        )

        if val_data is not None:
            X_val, y_val, g_val = val_data
            self.model.fit(
                X,
                y,
                group=groups,
                eval_set=[(X_val, y_val)],
                eval_group=[g_val],
                callbacks=[lgb.early_stopping(20, verbose=False)],
            )
        else:
            self.model.fit(X, y, group=groups)

    def _fit_regressor(self, X: np.ndarray, y: np.ndarray, val_data: tuple | None) -> None:
        self.model = lgb.LGBMRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=0.8,
            colsample_bytree=0.8,
            verbose=-1,
            n_jobs=-1,
        )

        if val_data is not None:
            X_val, y_val, _ = val_data
            self.model.fit(
                X,
                y,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(20, verbose=False)],
            )
        else:
            self.model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted or self.model is None:
            raise RuntimeError("模型未训练")
        return self.model.predict(X)

    def save(self, path: str) -> None:
        if self.model is not None:
            self.model.booster_.save_model(path)

    def load(self, path: str) -> None:
        if self.model is None:
            self.model = lgb.LGBMRanker()
        self.model._Booster = lgb.Booster(model_file=path)
        self._fitted = True


__all__ = ["LightGBMModel"]
