"""机器学习模型（LightGBM / XGBoost）"""
from __future__ import annotations

try:
    from .lightgbm_model import LightGBMModel
except ImportError:
    pass

try:
    from .xgboost_model import XGBoostModel
except ImportError:
    pass
