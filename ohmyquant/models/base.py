"""ML/DL/RL 模型抽象基类与训练管道

Model ABC 独立于选股器，可复用于信号生成、风险预测等场景。
FeaturePipeline 与 Model 解耦，支持链式特征变换。
TrainingPipeline 封装训练/推理分离逻辑。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


class Model(ABC):
    """模型抽象基类

    所有 ML/DL/RL 模型实现此接口。通过 register_model 装饰器注册。
    独立于选股器，可复用于信号生成、风险预测等场景。

    Usage:
        @register_model("lightgbm_ltr")
        class LightGBMModel(Model):
            def fit(self, X, y, groups=None, val_data=None): ...
            def predict(self, X): ...
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._fitted = False

    @abstractmethod
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray | None = None,
        val_data: tuple[np.ndarray, np.ndarray, np.ndarray | None] | None = None,
    ) -> None:
        """训练模型

        Args:
            X: 特征矩阵 (n_samples, n_features)
            y: 标签 (n_samples,)
            groups: 分组信息（LTR 用），每组一个 query
            val_data: 验证集 (X_val, y_val, groups_val)
        """
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测得分

        Args:
            X: 特征矩阵 (n_samples, n_features)

        Returns:
            预测得分 (n_samples,)
        """
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """保存模型"""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """加载模型"""
        ...

    @property
    def fitted(self) -> bool:
        return self._fitted


class FeaturePipeline:
    """链式特征变换器

    将多个特征变换器串联，支持 fit_transform 和 transform。
    变换器定义在 features.py 中。

    Usage:
        pipeline = FeaturePipeline()
        pipeline.add_transform("rank")
        pipeline.add_transform("zscore")
        pipeline.add_transform("winsorize", lower=0.01, upper=0.99)
        X = pipeline.fit_transform(df)
    """

    def __init__(self):
        self._transforms: list[tuple[str, dict]] = []
        self._fitted_transforms: list[Any] = []

    def add_transform(self, name: str, **kwargs) -> "FeaturePipeline":
        """添加变换器

        Args:
            name: 变换器名称（rank/zscore/winsorize/industry_neutral/lag）
            **kwargs: 变换器参数
        """
        self._transforms.append((name, kwargs))
        return self

    def fit_transform(self, df: pl.DataFrame, feature_names: list[str] | None = None) -> np.ndarray:
        """拟合并变换

        Args:
            df: 包含 code 列和因子列的 DataFrame
            feature_names: 使用的因子列名，None 则自动选择数值列

        Returns:
            特征矩阵 (n_samples, n_features)
        """
        from .features import create_transform

        if feature_names is None:
            feature_names = [
                c for c in df.columns
                if c not in ("code", "date") and df[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
            ]

        self._feature_names = feature_names
        self._fitted_transforms = []
        current_df = df.select(["code"] + feature_names)

        for name, kwargs in self._transforms:
            transform = create_transform(name, **kwargs)
            current_df = transform.fit_transform(current_df, feature_names)
            self._fitted_transforms.append(transform)

        return current_df.drop("code").to_numpy()

    def transform(self, df: pl.DataFrame) -> np.ndarray:
        """用已拟合的变换器变换新数据"""
        current_df = df.select(["code"] + self._feature_names)
        for transform in self._fitted_transforms:
            current_df = transform.transform(current_df, self._feature_names)
        return current_df.drop("code").to_numpy()

    @property
    def feature_names(self) -> list[str]:
        return getattr(self, "_feature_names", [])


class TrainingPipeline:
    """训练/推理分离管道

    封装 Model + FeaturePipeline，提供统一的训练和预测接口。
    支持滚动训练（walk-forward）。

    Usage:
        model = LightGBMModel(config)
        features = FeaturePipeline().add_transform("rank").add_transform("zscore")
        pipeline = TrainingPipeline(model, features)
        pipeline.train(factors, fwd_returns, stock_codes, current_idx)
        scores = pipeline.predict(factors, stock_codes, current_idx)
    """

    def __init__(
        self,
        model: Model,
        feature_pipeline: FeaturePipeline | None = None,
        config: dict | None = None,
    ):
        self.model = model
        self.feature_pipeline = feature_pipeline or FeaturePipeline()
        self.config = config or {}
        self.train_window = self.config.get("train_window", 252)
        self.target_horizon = self.config.get("target_horizon", 20)
        self.sample_step = self.config.get("sample_step", 5)
        self._last_train_idx = -999
        self._retrain_freq = self.config.get("retrain_freq", 21)

    def _build_cross_section(
        self,
        factors: dict[str, pl.DataFrame],
        stock_codes: list[str],
        idx: int,
    ) -> pl.DataFrame | None:
        """构建截面特征 DataFrame

        从因子宽表中提取 idx 时刻的截面数据。
        """
        if not self.feature_pipeline.feature_names:
            return None

        data: dict[str, Any] = {"code": stock_codes}
        for fname in self.feature_pipeline.feature_names:
            if fname not in factors:
                data[fname] = [None] * len(stock_codes)
                continue

            factor_df = factors[fname]
            if idx >= len(factor_df):
                data[fname] = [None] * len(stock_codes)
                continue

            row = factor_df.row(idx, named=True)
            vals = []
            for code in stock_codes:
                if code in row and row[code] is not None:
                    v = row[code]
                    vals.append(float(v) if isinstance(v, (int, float)) else None)
                else:
                    vals.append(None)
            data[fname] = vals

        return pl.DataFrame(data)

    def _build_training_data(
        self,
        factors: dict[str, pl.DataFrame],
        fwd_returns: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
        """构建训练数据（多截面采样）"""
        lookback_start = max(0, current_idx - self.train_window)
        horizon = self.target_horizon

        if current_idx + horizon >= len(fwd_returns):
            return None, None, None

        all_X: list[np.ndarray] = []
        all_y: list[float] = []
        all_groups: list[int] = []

        sample_indices = list(range(lookback_start, current_idx - horizon, self.sample_step))
        for idx in sample_indices:
            if idx + horizon >= len(fwd_returns):
                continue

            feat_df = self._build_cross_section(factors, stock_codes, idx)
            if feat_df is None or len(feat_df) < 20:
                continue

            ret_row = fwd_returns.row(idx + horizon, named=True)
            label_vals: list[float] = []
            valid_codes: list[str] = []
            for code in feat_df["code"].to_list():
                if code in ret_row and ret_row[code] is not None:
                    v = ret_row[code]
                    if isinstance(v, (int, float)) and not np.isnan(v):
                        label_vals.append(float(v))
                        valid_codes.append(code)

            if len(label_vals) < 20:
                continue

            feat_df = feat_df.filter(pl.col("code").is_in(valid_codes))
            X = self.feature_pipeline.fit_transform(feat_df)
            all_X.append(X)
            all_y.extend(label_vals)
            all_groups.append(len(label_vals))

        if not all_X:
            return None, None, None

        X = np.vstack(all_X)
        y = np.array(all_y)
        groups = np.array(all_groups)

        if self.model.__class__.__name__ in ("LightGBMModel", "XGBoostModel"):
            y_int = self._discretize_labels(y, groups, n_bins=5)
            return X, y_int, groups
        return X, y, groups

    @staticmethod
    def _discretize_labels(y: np.ndarray, groups: np.ndarray, n_bins: int = 5) -> np.ndarray:
        """将连续收益标签离散化为排名等级（LTR 用）"""
        y_int = np.zeros_like(y, dtype=int)
        start = 0
        for g in groups:
            end = start + g
            segment = y[start:end]
            ranks = np.argsort(np.argsort(segment)) / len(segment)
            y_int[start:end] = np.clip((ranks * n_bins).astype(int), 0, n_bins - 1)
            start = end
        return y_int

    def train(
        self,
        factors: dict[str, pl.DataFrame],
        fwd_returns: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        force: bool = False,
    ) -> bool:
        """训练模型

        Args:
            factors: 因子宽表 {name: wide_df}
            fwd_returns: 前向收益宽表
            stock_codes: 股票代码列表
            current_idx: 当前时间索引
            force: 是否强制重训练

        Returns:
            是否实际执行了训练
        """
        need_retrain = force or (
            not self.model.fitted
            or (current_idx - self._last_train_idx) >= self._retrain_freq
        )
        if not need_retrain:
            return False

        X, y, groups = self._build_training_data(factors, fwd_returns, stock_codes, current_idx)
        if X is None or len(X) < 100:
            return False

        val_data = None
        if groups is not None and len(groups) > 4:
            split_group = int(len(groups) * 0.8)
            split_idx = int(groups[:split_group].sum())
            val_data = (X[split_idx:], y[split_idx:], groups[split_group:])

        try:
            self.model.fit(X[:split_idx] if val_data else X, y[:split_idx] if val_data else y,
                           groups[:split_group] if val_data else groups, val_data=val_data)
            self._last_train_idx = current_idx
            logger.debug(f"模型训练完成: {len(X)} 样本, {len(groups) if groups is not None else 0} 组")
            return True
        except Exception as e:
            logger.warning(f"模型训练失败: {e}")
            return False

    def predict(
        self,
        factors: dict[str, pl.DataFrame],
        stock_codes: list[str],
        current_idx: int,
    ) -> dict[str, float] | None:
        """预测截面得分

        Returns:
            {code: score} 或 None
        """
        if not self.model.fitted:
            return None

        feat_df = self._build_cross_section(factors, stock_codes, current_idx)
        if feat_df is None or len(feat_df) == 0:
            return None

        try:
            X = self.feature_pipeline.transform(feat_df)
            scores = self.model.predict(X)
            codes = feat_df["code"].to_list()
            return dict(zip(codes, scores.tolist()))
        except Exception as e:
            logger.warning(f"模型预测失败: {e}")
            return None


__all__ = [
    "Model",
    "FeaturePipeline",
    "TrainingPipeline",
]
