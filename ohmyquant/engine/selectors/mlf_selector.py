"""ML 选因子选股器（两阶段）

Stage 1: LightGBM 预测每个因子未来一月的 IC，选出 top-K 因子
Stage 2: ICIR 加权在选定因子上选股

融入 2026 H1 研报创新点:
  - 因子拥挤度特征 (华泰 2026-03《量化行业轮动的崎岖之路》)
  - 市场状态条件特征 (MRA-AGRU 2026-03 Market Regime Aware)
  - 收益截面中性化 (国海金工 2026-05 涨跌幅中性化)
"""
from __future__ import annotations

import glob
import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ...data.base import DataSource
from ...factors.analysis import FactorAnalyzer
from ...factors.optimizer import FactorOptimizer
from ..selector import BaseSelector

logger = get_logger(__name__)

try:
    import lightgbm as lgb

    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    logger.info("LightGBM 未安装，MLF选股不可用")


FEATURE_NAMES = [
    "ic_20d", "ic_60d", "ic_120d", "ic_std", "icir",
    "ic_momentum", "crowding",
    "regime_vol_pct", "regime_trend", "regime_momentum",
]


@register_selector("mlf")
class MLFSelector(BaseSelector):
    """两阶段 ML 选因子选股器

    Stage 1: LightGBM 预测因子下月 IC → 选 top-K 因子
    Stage 2: ICIR 加权在选定因子上选股

    配置 selection.mlf:
      data_root: 因子数据根目录
      top_k_factors: 选出的因子数 (默认 30)
      train_window: ML 训练窗口 (默认 756, 约 3 年)
      retrain_freq: 重训练频率 (默认 21 天)
      target_horizon: IC 预测周期 (默认 20 天)
      neutralize: 是否对前向收益做截面中性化 (默认 True)
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        mlf_cfg = self.config.get("mlf", {})
        self.data_root = mlf_cfg.get(
            "data_root", "D:/Work/Project/download_a_share/data"
        )
        self.top_k_factors = mlf_cfg.get("top_k_factors", 30)
        self.train_window = mlf_cfg.get("train_window", 756)
        self.retrain_freq = mlf_cfg.get("retrain_freq", 21)
        self.target_horizon = mlf_cfg.get("target_horizon", 20)
        self.neutralize = mlf_cfg.get("neutralize", True)
        self.max_industry_weight = mlf_cfg.get("max_industry_weight", 0.0)
        self.max_stocks_per_industry = mlf_cfg.get("max_stocks_per_industry", 0)
        self._cache_dir = mlf_cfg.get("cache_dir", "output/cache")

        self._factor_names: list[str] | None = None
        self._ic_cache: pl.DataFrame | None = None
        self._regime_features: pl.DataFrame | None = None
        self._model = None
        self._last_train_idx = -999
        self._dates: list[str] | None = None
        self._industry_map: dict[str, str] | None = None

    def select_strong_factors(
        self, ic_df: pl.DataFrame, train_end: str
    ) -> list[str]:
        """占位符 — MLF selector 自行选因子，绕过引擎的强因子筛选"""
        return ["__mlf__"]

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
        if not HAS_LGB or fwd_returns is None:
            return None

        if self._ic_cache is None:
            self._build_ic_cache(close, stock_codes, fwd_returns)

        if self._ic_cache is None or self._dates is None:
            return None

        if current_idx >= len(self._dates):
            return None

        need_retrain = (
            self._model is None
            or (current_idx - self._last_train_idx) >= self.retrain_freq
        )
        if need_retrain:
            self._train_ml_model(current_idx)
            self._last_train_idx = current_idx

        if self._model is None:
            selected = self._fallback_select_factors(current_idx)
        else:
            selected = self._predict_and_select_factors(current_idx)

        if not selected:
            return None

        factors_wide: dict[str, pl.DataFrame] = {}
        for fname in selected:
            fw = self._load_factor_wide(fname, stock_codes)
            if fw is not None:
                factors_wide[fname] = fw

        if not factors_wide:
            return None

        return self._icir_select(
            list(factors_wide.keys()), factors_wide, stock_codes, current_idx
        )

    # ------------------------------------------------------------------
    # 因子数据加载
    # ------------------------------------------------------------------

    def _discover_factor_names(self) -> list[str]:
        factors_dir = os.path.join(self.data_root, "parquet", "factors")
        if not os.path.isdir(factors_dir):
            logger.warning(f"因子目录不存在: {factors_dir}")
            return []
        return sorted(
            d
            for d in os.listdir(factors_dir)
            if os.path.isdir(os.path.join(factors_dir, d))
        )

    def _load_factor_wide(
        self,
        factor_name: str,
        stock_codes: list[str],
    ) -> pl.DataFrame | None:
        """读取单个因子，返回 date × code 宽表（常规代码格式）"""
        factor_dir = os.path.join(
            self.data_root, "parquet", "factors", factor_name
        )
        if not os.path.isdir(factor_dir):
            return None

        parquet_files = sorted(
            glob.glob(os.path.join(factor_dir, "year=*", "data.parquet"))
        )
        if not parquet_files:
            return None

        # 只读 year=2018 及以后（因子数据 2007-2017 缺失，2005/2006 不用）
        parquet_files = [
            pf
            for pf in parquet_files
            if int(os.path.basename(os.path.dirname(pf)).split("=")[1]) >= 2018
        ]
        if not parquet_files:
            return None

        jq_codes = {DataSource.normalize_code(c) for c in stock_codes}

        dfs = []
        for pf in parquet_files:
            try:
                df = pl.read_parquet(pf)
                df = df.filter(pl.col("code").is_in(list(jq_codes)))
                if len(df) > 0:
                    dfs.append(df)
            except Exception as e:
                logger.debug(f"读取因子 {factor_name} {pf} 失败: {e}")

        if not dfs:
            return None

        combined = pl.concat(dfs)

        # 聚宽代码 → 常规代码
        combined = combined.with_columns(
            pl.col("code")
            .map_elements(DataSource.denormalize_code, return_dtype=pl.Utf8)
            .alias("code")
        )

        # 只保留 _dates 范围内的日期（用 date 对象比较，避免字符串格式问题）
        if self._dates:
            from datetime import datetime as _dt

            start_d = _dt.strptime(self._dates[0][:10], "%Y-%m-%d").date()
            end_d = _dt.strptime(self._dates[-1][:10], "%Y-%m-%d").date()
            combined = combined.filter(
                (pl.col("date") >= start_d) & (pl.col("date") <= end_d)
            )

        if len(combined) == 0:
            return None

        wide = combined.pivot(
            values=factor_name, index="date", on="code"
        ).sort("date")

        # 对齐到 IC 缓存日期（确保 current_idx 索引一致）
        if self._ic_cache is not None:
            cache_dates = self._ic_cache.select("date")
            # 统一日期类型
            if wide.schema["date"] != cache_dates.schema["date"]:
                wide = wide.with_columns(
                    pl.col("date").cast(cache_dates.schema["date"])
                )
            wide = cache_dates.join(wide, on="date", how="left")

        return wide

    # ------------------------------------------------------------------
    # IC 缓存构建
    # ------------------------------------------------------------------

    def _build_ic_cache(
        self,
        close: pl.DataFrame,
        stock_codes: list[str],
        fwd_returns: pl.DataFrame,
    ) -> None:
        """流式加载 260 因子，逐个计算 IC，合并为 date × 260 宽表

        首次计算后保存到 parquet 缓存，后续运行直接加载。
        """
        dates = fwd_returns["date"].to_list()
        self._dates = [
            d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            for d in dates
        ]

        # 缓存键含股票池哈希，区分不同池
        codes_signature = hashlib.md5(
            "|".join(sorted(stock_codes)).encode()
        ).hexdigest()[:8]
        cache_key = f"ic_cache_{codes_signature}_{self._dates[0]}_{self._dates[-1]}"
        cache_path = Path(self._cache_dir) / f"{cache_key}.parquet"

        # 向后兼容: 旧的 csi300 硬编码缓存
        if not cache_path.exists():
            legacy_path = Path(self._cache_dir) / f"ic_cache_csi300_{self._dates[0]}_{self._dates[-1]}.parquet"
            if legacy_path.exists():
                cache_path = legacy_path

        if cache_path.exists():
            logger.info(f"加载 IC 缓存: {cache_path}")
            self._ic_cache = pl.read_parquet(cache_path)
            self._factor_names = [
                c for c in self._ic_cache.columns if c != "date"
            ]
            self._regime_features = self._compute_regime_features(close)
            logger.info(
                f"IC 缓存已加载: {self._ic_cache.shape[0]} 天 × "
                f"{self._ic_cache.shape[1] - 1} 因子"
            )
            return

        logger.info("开始构建 IC 缓存...")

        self._factor_names = self._discover_factor_names()
        if not self._factor_names:
            logger.warning("未发现因子数据")
            return

        n_factors = len(self._factor_names)
        logger.info(f"发现 {n_factors} 个因子")

        # 截面中性化前向收益
        if self.neutralize:
            fwd_returns = self._neutralize_returns(fwd_returns)

        # 流式计算每个因子的 IC（向量化版本）
        # 用 date 列作为基准，逐因子 left join 对齐（因子日期可能少于 fwd_returns）
        base_df = fwd_returns.select("date")
        ic_df = base_df

        for i, fname in enumerate(self._factor_names):
            if i % 50 == 0:
                logger.info(f"IC 缓存进度: {i}/{n_factors} ({fname})")

            fw = self._load_factor_wide(fname, stock_codes)
            if fw is None:
                ic_df = ic_df.with_columns(
                    pl.lit(None).alias(fname)
                )
                continue

            try:
                ic_series = FactorAnalyzer.compute_ic_vectorized(
                    fw, fwd_returns
                )
                ic_series = ic_series.rename({"ic": fname})
                # 统一日期类型以确保 join 匹配
                if ic_series.schema["date"] != ic_df.schema["date"]:
                    ic_series = ic_series.with_columns(
                        pl.col("date").cast(ic_df.schema["date"])
                    )
                ic_df = ic_df.join(ic_series, on="date", how="left")
            except Exception as e:
                logger.debug(f"因子 {fname} IC 计算失败: {e}")
                ic_df = ic_df.with_columns(
                    pl.lit(None).alias(fname)
                )

        self._ic_cache = ic_df
        self._regime_features = self._compute_regime_features(close)
        logger.info(
            f"IC 缓存构建完成: {self._ic_cache.shape[0]} 天 × "
            f"{self._ic_cache.shape[1] - 1} 因子"
        )

        # 保存缓存
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._ic_cache.write_parquet(cache_path)
        logger.info(f"IC 缓存已保存: {cache_path}")

    @staticmethod
    def _neutralize_returns(fwd_returns: pl.DataFrame) -> pl.DataFrame:
        """前向收益截面去均值（移除市场整体收益成分）

        参考国海金工 2026 涨跌幅中性化，简化为截面均值去除。
        """
        cols = [c for c in fwd_returns.columns if c != "date"]
        row_mean = pl.mean_horizontal([pl.col(c) for c in cols])
        return fwd_returns.with_columns(
            (pl.col(c) - row_mean).alias(c) for c in cols
        )

    def _compute_regime_features(self, close: pl.DataFrame) -> pl.DataFrame:
        """计算市场状态特征（波动率分位、趋势强度、动量）

        参考 MRA-AGRU 2026 Market Regime Aware 动态因子门控。
        """
        dates = close["date"]
        cols = [c for c in close.columns if c != "date"]

        # 等权市场代理
        close_eq = close.select(
            pl.mean_horizontal([pl.col(c) for c in cols]).alias("eq_close")
        )["eq_close"].to_numpy()

        mkt_ret = np.zeros(len(close_eq))
        mkt_ret[1:] = close_eq[1:] / close_eq[:-1] - 1
        mkt_ret[0] = 0

        # 滚动 20d 波动率
        vol_20d = np.full(len(mkt_ret), np.nan)
        for i in range(20, len(mkt_ret)):
            vol_20d[i] = np.std(mkt_ret[i - 20 : i])

        # 波动率分位（vs 252d 窗口）
        vol_pct = np.full(len(mkt_ret), 0.5)
        for i in range(252, len(mkt_ret)):
            window = vol_20d[max(0, i - 252) : i]
            valid = window[~np.isnan(window)]
            if len(valid) > 10 and not np.isnan(vol_20d[i]):
                vol_pct[i] = float(np.mean(valid <= vol_20d[i]))

        # 趋势: 20d MA / 60d MA - 1
        trend = np.zeros(len(mkt_ret))
        for i in range(60, len(mkt_ret)):
            ma20 = np.mean(close_eq[i - 20 : i])
            ma60 = np.mean(close_eq[i - 60 : i])
            trend[i] = (ma20 - ma60) / ma60 if ma60 > 0 else 0

        # 动量: 20d 累计收益
        momentum = np.zeros(len(mkt_ret))
        for i in range(20, len(mkt_ret)):
            momentum[i] = (
                close_eq[i] / close_eq[i - 20] - 1
                if close_eq[i - 20] > 0
                else 0
            )

        return pl.DataFrame(
            {
                "date": dates,
                "vol_pct": vol_pct,
                "trend": trend,
                "momentum": momentum,
            }
        )

    # ------------------------------------------------------------------
    # ML 模型训练与预测
    # ------------------------------------------------------------------

    def _train_ml_model(self, current_idx: int) -> None:
        """训练 LightGBM 回归器预测因子下月 IC"""
        h = self.target_horizon
        lookback_start = max(0, current_idx - self.train_window)

        if current_idx < 2 * h + 120:
            logger.warning(
                f"训练数据不足: current_idx={current_idx}, 需要至少 {2 * h + 120}"
            )
            return

        X_list: list[list[float]] = []
        y_list: list[float] = []

        sample_indices = list(range(lookback_start, current_idx - 2 * h, 5))

        for idx in sample_indices:
            if idx + 2 * h >= len(self._dates):
                continue

            # 预计算该日期所有因子的 IC 值（用于 rank 特征）
            ic_row = self._ic_cache.row(idx - h, named=True) if idx - h >= 0 else {}

            for fname in self._factor_names:
                feat = self._build_factor_features(fname, idx, ic_row)
                if feat is None:
                    continue

                # 标签: [idx+h, idx+2h] 的 IC 均值（在 current_idx 前已完全实现）
                ic_col = self._ic_cache[fname]
                future_ic = ic_col[idx + h : idx + 2 * h].drop_nulls()
                if len(future_ic) < 5:
                    continue

                X_list.append(feat)
                y_list.append(float(future_ic.mean()))

        if len(X_list) < 200:
            logger.warning(f"训练样本不足: {len(X_list)}")
            return

        X = np.array(X_list)
        y = np.array(y_list)

        split = int(len(X) * 0.8)

        try:
            self._model = lgb.LGBMRegressor(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                verbose=-1,
                n_jobs=-1,
            )
            self._model.fit(
                X[:split],
                y[:split],
                eval_set=[(X[split:], y[split:])],
                callbacks=[lgb.early_stopping(20, verbose=False)],
            )
            logger.info(
                f"ML 模型训练完成: {len(X_list)} 样本, {len(self._factor_names)} 因子"
            )
        except Exception as e:
            logger.warning(f"ML 训练失败: {e}")
            self._model = None

    def _build_factor_features(
        self,
        fname: str,
        idx: int,
        ic_row: dict | None = None,
    ) -> list[float] | None:
        """构建因子在 idx 时刻的 ML 特征

        特征使用 IC up to idx - target_horizon（防前视）
        """
        h = self.target_horizon
        feat_end = idx - h
        if feat_end < 120:
            return None

        ic_col = self._ic_cache[fname]
        ic_vals = (
            ic_col[max(0, feat_end - 120) : feat_end].drop_nulls().to_numpy()
        )

        if len(ic_vals) < 60:
            return None

        ic_20d = (
            float(np.mean(ic_vals[-20:]))
            if len(ic_vals) >= 20
            else float(np.mean(ic_vals))
        )
        ic_60d = (
            float(np.mean(ic_vals[-60:]))
            if len(ic_vals) >= 60
            else float(np.mean(ic_vals))
        )
        ic_120d = float(np.mean(ic_vals))
        ic_std = float(np.std(ic_vals))
        icir = ic_60d / ic_std if ic_std > 1e-8 else 0.0

        # IC 动量: 近 20d 均值 - 前 20d 均值
        if len(ic_vals) >= 40:
            ic_momentum = float(np.mean(ic_vals[-20:]) - np.mean(ic_vals[-40:-20]))
        else:
            ic_momentum = 0.0

        # 拥挤度: 近期 IC / 历史 IC (参考华泰 2026 拥挤度监控)
        crowding = (
            ic_20d / (ic_120d + 1e-8) if abs(ic_120d) > 1e-6 else 1.0
        )

        # 市场状态特征
        if self._regime_features is not None and feat_end < len(
            self._regime_features
        ):
            rf = self._regime_features.row(feat_end, named=True)
            vol_pct = float(rf.get("vol_pct", 0.5) or 0.5)
            trend = float(rf.get("trend", 0) or 0)
            momentum = float(rf.get("momentum", 0) or 0)
        else:
            vol_pct, trend, momentum = 0.5, 0.0, 0.0

        return [
            ic_20d,
            ic_60d,
            ic_120d,
            ic_std,
            icir,
            ic_momentum,
            crowding,
            vol_pct,
            trend,
            momentum,
        ]

    def _predict_and_select_factors(self, current_idx: int) -> list[str]:
        """预测所有因子下月 IC，选 top-K

        用预测 IC 绝对值排序（负 IC 因子也有用，做反向）。
        方向在 _icir_select 中通过 _get_ic_direction 自动处理。
        """
        h = self.target_horizon
        feat_end = current_idx - h

        if feat_end < 120:
            return self._fallback_select_factors(current_idx)

        ic_row = (
            self._ic_cache.row(feat_end, named=True)
            if feat_end < len(self._ic_cache)
            else {}
        )

        predictions: list[tuple[str, float]] = []
        for fname in self._factor_names:
            feat = self._build_factor_features(fname, current_idx, ic_row)
            if feat is None:
                continue
            pred = float(self._model.predict([feat])[0])
            predictions.append((fname, pred))

        if not predictions:
            return self._fallback_select_factors(current_idx)

        # 按预测 IC 绝对值排序（负 IC 因子也有用，做反向）
        predictions.sort(key=lambda x: abs(x[1]), reverse=True)
        selected = [f for f, _ in predictions[: self.top_k_factors]]

        pos_count = sum(1 for _, v in predictions[: self.top_k_factors] if v > 0)
        pred_values = [v for _, v in predictions[: self.top_k_factors]]
        logger.info(
            f"ML 选因子: top-{len(selected)}, "
            f"预测IC [{min(pred_values):.4f}, {max(pred_values):.4f}], "
            f"正IC因子 {pos_count}/{len(selected)}"
        )
        return selected

    def _fallback_select_factors(self, current_idx: int) -> list[str]:
        """退化方案：按近期 ICIR 绝对值选因子"""
        h = self.target_horizon
        feat_end = current_idx - h

        factor_icir: list[tuple[str, float]] = []
        for fname in self._factor_names:
            ic_col = self._ic_cache[fname]
            ic_vals = (
                ic_col[max(0, feat_end - 60) : feat_end].drop_nulls().to_numpy()
            )
            if len(ic_vals) < 10:
                continue
            ic_mean = float(np.mean(ic_vals))
            ic_std = float(np.std(ic_vals))
            icir = ic_mean / ic_std if ic_std > 1e-8 else 0.0
            factor_icir.append((fname, abs(icir)))

        factor_icir.sort(key=lambda x: x[1], reverse=True)
        selected = [f for f, _ in factor_icir[: self.top_k_factors]]
        logger.info(f"退化选因子 (ICIR): top-{len(selected)}")
        return selected

    # ------------------------------------------------------------------
    # ICIR 选股
    # ------------------------------------------------------------------

    def _load_industry_map(self) -> dict[str, str]:
        """加载申万一级行业分类（code → industry）"""
        if self._industry_map is not None:
            return self._industry_map

        ind_file = os.path.join(
            self.data_root, "parquet", "stock_industry", "year=2026", "data.parquet"
        )
        if not os.path.exists(ind_file):
            logger.warning(f"行业数据不存在: {ind_file}")
            self._industry_map = {}
            return self._industry_map

        df = pl.read_parquet(ind_file)
        self._industry_map = {}
        for row in df.iter_rows(named=True):
            jq_code = row.get("code", "")
            code = DataSource.denormalize_code(jq_code)
            industry = row.get("sw_l1_name") or "未分类"
            self._industry_map[code] = industry

        logger.info(f"行业数据加载: {len(self._industry_map)} 只股票")
        return self._industry_map

    def _apply_industry_cap(
        self,
        weights: dict[str, float],
        max_industry: float,
        max_stock: float = 0.0,
    ) -> dict[str, float]:
        """行业暴露上限约束：迭代缩放超限行业，excess 按可用容量分配

        关键：分配 excess 时尊重个股权重上限 (max_stock)，避免将个股
        推过 4% 后被 backtest engine 的 portfolio_optimizer.apply_weight_cap
        再次截断并 redistributed 回超限行业（undo 行业约束）。

        无法分配的 excess 保留为现金（总权重 < 1，不归一化）。
        """
        if max_industry <= 0 or not weights:
            return weights

        industry_map = self._load_industry_map()

        for _ in range(20):
            # 计算各行业权重
            ind_weights: dict[str, float] = {}
            for code, w in weights.items():
                ind = industry_map.get(code, "未分类")
                ind_weights[ind] = ind_weights.get(ind, 0) + w

            # 找超限行业（容差 1e-6）
            over_industries = {
                ind for ind, w in ind_weights.items() if w > max_industry + 1e-6
            }
            if not over_industries:
                break

            # 缩放超限行业到 max_industry
            excess = 0.0
            for code in weights:
                ind = industry_map.get(code, "未分类")
                if ind in over_industries:
                    scale = max_industry / ind_weights[ind]
                    excess += weights[code] * (1 - scale)
                    weights[code] *= scale

            if excess <= 1e-9:
                break

            # 计算未超限行业的可用容量（考虑个股权重上限）
            stock_room: dict[str, float] = {}
            ind_room: dict[str, float] = {}
            for code, w in weights.items():
                ind = industry_map.get(code, "未分类")
                if ind not in over_industries:
                    room = (max_stock - w) if max_stock > 0 else float("inf")
                    room = max(0, room)
                    if room > 1e-9:
                        stock_room[code] = room
                        ind_room[ind] = ind_room.get(ind, 0) + room

            total_room = sum(ind_room.values())
            if total_room <= 1e-9:
                break  # 无可用容量，excess 保留为现金

            # 按行业可用容量比例分配 excess
            distributable = min(excess, total_room)
            for ind, ind_cap in ind_room.items():
                ind_share = ind_cap / total_room * distributable
                ind_total = ind_weights.get(ind, 0)
                if ind_total <= 0:
                    continue
                for code in weights:
                    if (
                        industry_map.get(code, "未分类") == ind
                        and code in stock_room
                    ):
                        add = ind_share * (weights[code] / ind_total)
                        # 不超过个股权重上限
                        add = min(add, stock_room[code])
                        weights[code] += add

        return weights

    def _icir_select(
        self,
        selected_factors: list[str],
        factors_wide: dict[str, pl.DataFrame],
        stock_codes: list[str],
        current_idx: int,
    ) -> dict[str, float] | None:
        """ICIR 加权选股（复用 ICIRSelector 模式）"""
        if not selected_factors or self._dates is None:
            return None

        if current_idx >= len(self._dates):
            return None

        current_date = self._ic_cache["date"][current_idx]

        # 构建 mini ic_df 供 ICIR 权重计算
        ic_cols: dict[str, Any] = {"date": self._ic_cache["date"]}
        for fname in selected_factors:
            if fname in self._ic_cache.columns:
                ic_cols[fname] = self._ic_cache[fname]
        mini_ic_df = pl.DataFrame(ic_cols)

        factor_weights = FactorOptimizer.compute_icir_weights(
            mini_ic_df,
            selected_factors,
            current_date,
            self.icir_window,
            self.ic_decay,
        )

        if not any(factor_weights.values()):
            factor_weights = {
                f: 1.0 / len(selected_factors) for f in selected_factors
            }

        scores: dict[str, float] = {code: 0.0 for code in stock_codes}
        total_weight = 0.0

        for fname, weight in factor_weights.items():
            if weight <= 0 or fname not in factors_wide:
                continue

            factor_df = factors_wide[fname]
            if current_idx >= len(factor_df):
                continue

            row = factor_df.row(current_idx, named=True)
            factor_vals: dict[str, float] = {}
            for code in stock_codes:
                if code in row and row[code] is not None:
                    val = row[code]
                    if isinstance(val, (int, float)) and not np.isnan(val):
                        factor_vals[code] = float(val)

            if len(factor_vals) < 5:
                continue

            ic_dir = self._get_ic_direction(mini_ic_df, fname, current_idx)

            sorted_vals = sorted(factor_vals.items(), key=lambda x: x[1])
            n = len(sorted_vals)
            for rank_idx, (code, _) in enumerate(sorted_vals):
                pct_rank = (rank_idx + 1) / n
                if ic_dir < 0:
                    pct_rank = 1 - pct_rank
                scores[code] += pct_rank * weight

            total_weight += weight

        if total_weight == 0:
            return None

        scores = {k: v / total_weight for k, v in scores.items()}
        scores = {k: v for k, v in scores.items() if v > 0}

        if not scores:
            return None

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 行业配额选股：限制每个行业的股票数量，确保行业多样性
        if self.max_stocks_per_industry > 0:
            industry_map = self._load_industry_map()
            ind_count: dict[str, int] = {}
            top_stocks = []
            for code, score in sorted_scores:
                ind = industry_map.get(code, "未分类")
                if ind_count.get(ind, 0) < self.max_stocks_per_industry:
                    top_stocks.append((code, score))
                    ind_count[ind] = ind_count.get(ind, 0) + 1
                if len(top_stocks) >= self.top_n:
                    break
            logger.info(
                f"行业配额选股: {len(top_stocks)} 只, "
                f"{len(ind_count)} 个行业, "
                f"top={max(ind_count.values())} bottom={min(ind_count.values())}"
            )
        else:
            top_stocks = sorted_scores[: self.top_n]

        total_score = sum(s for _, s in top_stocks)
        if total_score <= 0:
            weights = {
                code: 1.0 / len(top_stocks) for code, _ in top_stocks
            }
        else:
            weights = {code: s / total_score for code, s in top_stocks}

        weights = self.apply_weight_cap(weights)

        # 行业暴露上限约束（传入个股权重上限，避免分配 excess 时推过 4%）
        if self.max_industry_weight > 0:
            weights = self._apply_industry_cap(
                weights, self.max_industry_weight, self.max_stock_weight
            )
            # 不归一化：无法分配的 excess 保留为现金（总权重 < 1）
            # 归一化会按比例放大所有权重，导致个股超 4% 被 backtest 再次截断

        return weights

    @staticmethod
    def _get_ic_direction(
        ic_df: pl.DataFrame, factor_name: str, current_idx: int
    ) -> float:
        if factor_name not in ic_df.columns:
            return 1.0
        lookback = min(60, current_idx)
        if lookback < 5:
            return 1.0
        recent_ic = (
            ic_df[factor_name][
                max(0, current_idx - lookback) : current_idx
            ].drop_nulls()
        )
        if len(recent_ic) == 0:
            return 1.0
        return float(recent_ic.mean())


__all__ = ["MLFSelector"]
