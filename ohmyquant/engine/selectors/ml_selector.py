"""ML 选股器（LightGBM 排序学习）

基于 Learning-to-Rank 的选股器，需要 lightgbm。
不可用时 HybridSelector 会自动降级为纯 ICIR。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ..selector import BaseSelector

logger = get_logger(__name__)

try:
    import lightgbm as lgb

    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    logger.info("LightGBM 未安装，ML选股不可用")


@register_selector("ml")
class MLSelector(BaseSelector):
    """LightGBM Learning-to-Rank 选股器

    流程:
      1. 构建截面特征（因子排名 + z-score）
      2. 滚动训练 LGBMRanker
      3. 预测最新截面，取 Top-N
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        ml_cfg = self.config.get("ml", {})
        self.n_estimators = ml_cfg.get("n_estimators", 150)
        self.max_depth = ml_cfg.get("max_depth", 3)
        self.learning_rate = ml_cfg.get("learning_rate", 0.05)
        self.train_window = ml_cfg.get("train_window", 252)
        self.retrain_freq = ml_cfg.get("retrain_freq", 21)
        self.target_horizon = ml_cfg.get("target_horizon", 20)

        self.model = None
        self._last_train_idx = -999
        self._feature_names: list[str] = []

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        fwd_returns: pl.DataFrame | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        if not HAS_LGB or fwd_returns is None or not strong_factors:
            return None

        self._feature_names = [f for f in strong_factors if f in factors]
        if not self._feature_names:
            return None

        # 构建训练数据
        X_train, y_train, groups = self._build_ltr_data(
            factors, fwd_returns, stock_codes, current_idx
        )

        if X_train is None or len(X_train) < 200:
            return None

        # 判断是否需要重训练
        need_retrain = (
            self.model is None
            or (current_idx - self._last_train_idx) >= self.retrain_freq
        )
        if need_retrain:
            self._train_ltr(X_train, y_train, groups)
            self._last_train_idx = current_idx

        if self.model is None:
            return None

        # 预测最新截面
        X_pred, pred_stocks = self._build_prediction_features(
            factors, stock_codes, current_idx
        )
        if X_pred is None or len(X_pred) == 0:
            return None

        scores = self.model.predict(X_pred)

        # 取 Top-N
        score_pairs = list(zip(pred_stocks, scores))
        score_pairs.sort(key=lambda x: x[1], reverse=True)
        top = score_pairs[: self.top_n]

        # 过滤正分
        top = [(c, s) for c, s in top if s > 0]
        if not top:
            return None

        total = sum(s for _, s in top)
        weights = {c: s / total for c, s in top} if total > 0 else None
        return self.apply_weight_cap(weights) if weights else None

    def _build_ltr_data(
        self,
        factors: dict[str, pl.DataFrame],
        fwd_returns: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
        """构建 Learning-to-Rank 训练数据"""
        lookback_start = max(0, current_idx - self.train_window)
        horizon = self.target_horizon

        if current_idx + horizon >= len(fwd_returns):
            return None, None, None

        all_X: list[np.ndarray] = []
        all_y: list[int] = []
        all_groups: list[int] = []

        # 每5个交易日取一个截面
        sample_indices = list(range(lookback_start, current_idx - horizon, 5))
        for idx in sample_indices:
            if idx + horizon >= len(fwd_returns):
                continue

            feat_df = self._build_cross_section_features(factors, stock_codes, idx)
            if feat_df is None or len(feat_df) < 20:
                continue

            # 标签：未来N日收益排名
            ret_row = fwd_returns.row(idx + horizon, named=True)
            label_vals = []
            valid_codes = []
            for code in feat_df["code"].to_list():
                if code in ret_row and ret_row[code] is not None:
                    v = ret_row[code]
                    if isinstance(v, (int, float)) and not np.isnan(v):
                        label_vals.append(float(v))
                        valid_codes.append(code)

            if len(label_vals) < 20:
                continue

            feat_df = feat_df.filter(pl.col("code").is_in(valid_codes))

            # 收益排名离散化为5个等级
            y_rank = np.argsort(np.argsort(label_vals)) / len(label_vals)
            y_int = np.clip((y_rank * 5).astype(int), 0, 4)

            all_X.append(feat_df.drop("code").to_numpy())
            all_y.extend(y_int.tolist())
            all_groups.append(len(label_vals))

        if not all_X:
            return None, None, None

        X = np.vstack(all_X)
        y = np.array(all_y)
        groups = np.array(all_groups)
        return X, y, groups

    def _build_cross_section_features(
        self,
        factors: dict[str, pl.DataFrame],
        stock_codes: list[str],
        idx: int,
    ) -> pl.DataFrame | None:
        """构建截面特征：因子排名 + z-score"""
        data = {"code": stock_codes}
        for fname in self._feature_names:
            if fname not in factors:
                data[f"{fname}_rank"] = [0.5] * len(stock_codes)
                data[f"{fname}_zscore"] = [0.0] * len(stock_codes)
                continue

            factor_df = factors[fname]
            if idx >= len(factor_df):
                data[f"{fname}_rank"] = [0.5] * len(stock_codes)
                data[f"{fname}_zscore"] = [0.0] * len(stock_codes)
                continue

            row = factor_df.row(idx, named=True)
            vals = []
            for code in stock_codes:
                if code in row and row[code] is not None:
                    v = row[code]
                    vals.append(float(v) if isinstance(v, (int, float)) else None)
                else:
                    vals.append(None)

            # 排名和 z-score
            valid = [v for v in vals if v is not None and not np.isnan(v)]
            if len(valid) < 5:
                data[f"{fname}_rank"] = [0.5] * len(stock_codes)
                data[f"{fname}_zscore"] = [0.0] * len(stock_codes)
                continue

            mean_v = np.mean(valid)
            std_v = np.std(valid)

            ranks = []
            zscores = []
            for v in vals:
                if v is None or np.isnan(v):
                    ranks.append(0.5)
                    zscores.append(0.0)
                else:
                    # 简单百分位排名
                    rank = sum(1 for x in valid if x <= v) / len(valid)
                    ranks.append(rank)
                    zscores.append((v - mean_v) / std_v if std_v > 1e-8 else 0.0)

            data[f"{fname}_rank"] = ranks
            data[f"{fname}_zscore"] = zscores

        return pl.DataFrame(data)

    def _build_prediction_features(
        self,
        factors: dict[str, pl.DataFrame],
        stock_codes: list[str],
        current_idx: int,
    ) -> tuple[np.ndarray | None, list[str]]:
        """构建预测用截面特征"""
        feat_df = self._build_cross_section_features(factors, stock_codes, current_idx)
        if feat_df is None or len(feat_df) == 0:
            return None, []
        return feat_df.drop("code").to_numpy(), feat_df["code"].to_list()

    def _train_ltr(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
    ) -> None:
        """训练 Learning-to-Rank 模型"""
        try:
            # 按时间分割训练/验证
            total_groups = len(groups)
            split_group = int(total_groups * 0.8)
            split_idx = int(groups[:split_group].sum())

            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            g_train = groups[:split_group]
            g_val = groups[split_group:]

            self.model = lgb.LGBMRanker(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                learning_rate=self.learning_rate,
                subsample=0.8,
                colsample_bytree=0.8,
                verbose=-1,
                n_jobs=-1,
            )

            self.model.fit(
                X_train,
                y_train,
                group=g_train,
                eval_set=[(X_val, y_val)],
                eval_group=[g_val],
                callbacks=[lgb.early_stopping(20, verbose=False)],
            )
        except Exception as e:
            logger.warning(f"LTR 训练失败: {e}")
            self.model = None

    def select_strong_factors(self, ic_df: pl.DataFrame, train_end: str) -> list[str]:
        """ML 模式下因子筛选：IC 绝对值前15"""
        factor_cols = [c for c in ic_df.columns if c != "date"]
        train_ic = ic_df.filter(pl.col("date") <= pl.lit(train_end).str.to_date())
        ic_mean = train_ic.select([pl.col(c).mean() for c in factor_cols])
        # 取绝对值最大的15个
        means = {c: abs(ic_mean[c][0] or 0) for c in factor_cols}
        sorted_factors = sorted(means.items(), key=lambda x: x[1], reverse=True)
        return [f for f, _ in sorted_factors[:15]]


__all__ = ["MLSelector"]
