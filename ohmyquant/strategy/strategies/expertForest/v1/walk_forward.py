"""Walk Forward 滚动训练核心逻辑

时序规则:
  1. 训练区间 [t-window, t-purge_gap-1]，严格在预测日t之前
  2. purge_gap=5（与prediction_horizon一致），排除标签泄露的样本
  3. 预测日t的因子截面 → 预测 → t+1开盘价调仓
  4. 每周一调仓（weekday=0）

混合并行策略 (避免loky开销, 最大化CPU利用):
  Phase 1: LGB/XGB专家 — threading并行(释放GIL, 24模型同时训练)
  Phase 2: RF/ET专家 — 串行训练, 每模型n_jobs=-1使用全部32核
  - RF/ET受GIL限制无法threading并行, 但单模型用32核建树极快
  - LGB/XGB释放GIL可threading真并行, 单模型n_jobs=1够快

per-expert窗口:
  - 按(feature_set, train_window)分组预处理
  - 252天窗口专家用近1年数据，504天窗口专家用近2年数据
  - 各组独立Winsorize+Z-score，避免跨窗口统计量污染

IC计算 (抗过拟合):
  - 80/20时序holdout: 前80%训练, 后20%验证, 计算真实OOS IC
  - 避免in-sample IC过拟合(aggressive深树in-sample IC虚高)
  - 同一模型用于holdout验证和最终预测(保证IC与预测一致性)
"""
from __future__ import annotations

import gc
import time
import warnings
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl
from joblib import Parallel, delayed

from ohmyquant.core.logging import get_logger
from .expert_pool import ExpertConfig, build_expert_pool, create_model, filter_features

# 抑制LGBM feature names警告
warnings.filterwarnings("ignore", message="X does not have valid feature names")

logger = get_logger(__name__)


def train_one_expert(
    expert: ExpertConfig,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_pred: np.ndarray,
    n_jobs: int = -1,
    val_ratio: float = 0.2,
    need_ic: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """训练单个专家并返回(OOF验证预测, OOF验证标签, 预测集预测)

    抗过拟合: 用80/20时序holdout计算真实OOS IC
    - 前80%训练, 后20%作为holdout验证(时序, 避免未来信息泄漏)
    - 同一模型用于holdout验证和最终预测, 保证IC与预测一致性
    - 数据不足(<100样本)时退化为全量训练+in-sample验证
    - need_ic=False时(非IC集成方法)全量训练, 避免浪费数据
    """
    n = len(y_train)

    # 非IC集成方法(rank_average/equal_weight): 全量训练, 不需holdout
    # IC集成的数据不足退化路径也走全量训练
    if not need_ic or n < 100:
        model = create_model(expert, n_jobs=n_jobs)
        model.fit(X_train, y_train)
        train_preds = model.predict(X_train)
        preds = model.predict(X_pred)
        del model
        return train_preds, y_train, preds

    # IC集成方法: 80%训练 + 20%holdout验证
    split = int(n * (1 - val_ratio))
    if n - split < 20:
        model = create_model(expert, n_jobs=n_jobs)
        model.fit(X_train, y_train)
        train_preds = model.predict(X_train)
        preds = model.predict(X_pred)
        del model
        return train_preds, y_train, preds

    X_tr, X_val = X_train[:split], X_train[split:]
    y_tr, y_val = y_train[:split], y_train[split:]

    model = create_model(expert, n_jobs=n_jobs)
    model.fit(X_tr, y_tr)
    val_preds = model.predict(X_val)
    preds = model.predict(X_pred)
    del model
    return val_preds, y_val, preds


class WalkForwardTrainer:
    """Walk Forward 滚动训练器"""

    def __init__(
        self,
        factor_engine,
        expert_pool: list[ExpertConfig],
        config: dict,
    ):
        """
        Args:
            factor_engine: FactorEngine 实例
            expert_pool: 专家配置列表
            config: 策略配置
        """
        self.fe = factor_engine
        self.experts = expert_pool
        wf_cfg = config.get("walk_forward", {})
        self.rebalance_weekday = wf_cfg.get("rebalance_weekday", 0)
        self.prediction_horizon = wf_cfg.get("prediction_horizon", 5)
        self.purge_gap = wf_cfg.get("purge_gap", 5)
        # 混合并行策略: LGB/XGB用threading并行, RF/ET用n_jobs=-1全核串行
        # 避免loky的序列化/进程启动开销, 最大化CPU利用率
        self.n_jobs = config.get("expert", {}).get("n_jobs", 32)
        self.top_n = config.get("selection", {}).get("top_n", 10)
        self.ensemble_method = config.get("ensemble", {}).get("method", "equal_weight")

    def get_rebalance_dates(
        self, trade_calendar: list[str], start_date: str, end_date: str
    ) -> list[str]:
        """获取调仓日期列表（每周指定weekday）"""
        rebalance_dates = []
        for date_str in trade_calendar:
            if date_str < start_date or date_str > end_date:
                continue
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt.weekday() == self.rebalance_weekday:
                rebalance_dates.append(date_str)
        return rebalance_dates

    def run(
        self,
        data: dict[str, Any],
        start_date: str,
        end_date: str,
        trade_calendar: list[str],
    ) -> list[dict]:
        """执行Walk Forward滚动训练

        Returns:
            results: [{date, selected_codes, predictions, expert_predictions}]
        """
        factor_df: pl.DataFrame = data["factor_df"]
        label_df: pl.DataFrame = data["label_df"]
        price_df: pl.DataFrame = data["price_df"]
        factor_names: list[str] = data["factor_names"]
        pool_codes: list[str] = data["pool_codes"]

        # 合并因子和标签
        merged = factor_df.join(label_df, on=["date", "code"], how="inner")
        merged = merged.sort("date")

        # 获取所有日期列表
        all_dates = merged["date"].unique().sort().to_list()
        date_to_idx = {d: i for i, d in enumerate(all_dates)}

        # 调仓日
        rebalance_dates = self.get_rebalance_dates(
            trade_calendar, start_date, end_date
        )
        logger.info(f"Walk Forward: {len(rebalance_dates)} 个调仓日 ({rebalance_dates[0]} → {rebalance_dates[-1]})")

        results = []
        total = len(rebalance_dates)

        for i, rebalance_date in enumerate(rebalance_dates):
            t0 = time.time()
            dt = datetime.strptime(rebalance_date, "%Y-%m-%d").date()

            # 找到调仓日在all_dates中的位置
            if dt not in date_to_idx:
                logger.warning(f"调仓日 {rebalance_date} 不在因子数据中，跳过")
                continue
            t_idx = date_to_idx[dt]

            try:
                result = self._process_one_date(
                    rebalance_date, dt, t_idx, all_dates, merged,
                    factor_names, pool_codes,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"调仓日 {rebalance_date} 处理失败: {e}", exc_info=True)
                print(f"  [{i+1}/{total}] {rebalance_date} ERROR: {e}", flush=True)
                results.append({"date": rebalance_date, "selected_codes": [], "predictions": {}})

            # 释放本轮模型内存
            gc.collect()

            elapsed = time.time() - t0
            n_codes = len(results[-1]["selected_codes"]) if results else 0
            msg = (
                f"[{i+1}/{total}] {rebalance_date}: "
                f"选{n_codes}只, {elapsed:.1f}s"
            )
            logger.info(msg)
            print(f"  {msg}", flush=True)

        return results

    def _process_one_date(
        self,
        rebalance_date: str,
        dt,
        t_idx: int,
        all_dates: list,
        merged: pl.DataFrame,
        factor_names: list[str],
        pool_codes: list[str],
    ) -> dict:
        """处理单个调仓日：训练 → 预测 → 选股

        关键: 按(feature_set, train_window)分组，每组独立切片训练数据并预处理
        """
        # 1. 预测截面（调仓日当天的因子值）
        pred_data = merged.filter(pl.col("date") == pl.lit(dt))
        if len(pred_data) == 0:
            # 尝试最近的前一天
            for offset in range(1, 6):
                prev_idx = t_idx - offset
                if prev_idx >= 0:
                    pred_data = merged.filter(pl.col("date") == pl.lit(all_dates[prev_idx]))
                    if len(pred_data) > 0:
                        break
            if len(pred_data) == 0:
                logger.warning(f"{rebalance_date}: 无可用预测截面，跳过")
                return {"date": rebalance_date, "selected_codes": [], "predictions": {}}

        # 只保留在股票池中的股票
        pred_data = pred_data.filter(pl.col("code").is_in(pool_codes))
        if len(pred_data) < 5:
            logger.warning(f"{rebalance_date}: 池内股票数不足({len(pred_data)})，跳过")
            return {"date": rebalance_date, "selected_codes": [], "predictions": {}}

        # 2. 按(feature_set, train_window)分组，每组独立预处理
        groups: dict[tuple[str, int], list] = {}
        for expert in self.experts:
            key = (expert.feature_set, expert.train_window)
            if key not in groups:
                groups[key] = []
            groups[key].append(expert)

        # 3. 每组独立切片训练数据 + Winsorize + Z-score
        preprocessed: dict[tuple[str, int], tuple] = {}
        for (fs_name, window), exps in groups.items():
            # 按该组的窗口切片训练数据
            train_start_idx = max(0, t_idx - window)
            train_end_idx = max(0, t_idx - self.purge_gap)
            train_dates = all_dates[train_start_idx:train_end_idx]

            if len(train_dates) < 50:
                logger.warning(f"{rebalance_date}: 窗口{window}训练数据不足({len(train_dates)}天)")
                continue

            train_data = merged.filter(pl.col("date").is_in(train_dates))
            train_data = train_data.filter(pl.col("label").is_not_null())

            # 选择该特征集的因子
            fs_factors = filter_features(factor_names, exps[0].feature_prefixes)
            fs_factors = [f for f in fs_factors if f in train_data.columns]
            if len(fs_factors) == 0:
                continue

            # 训练集预处理: Winsorize + Z-score
            X_train_raw = train_data.select(fs_factors).to_numpy()
            lo = np.nanquantile(X_train_raw, self.fe.winsorize_q, axis=0)
            hi = np.nanquantile(X_train_raw, 1 - self.fe.winsorize_q, axis=0)
            clipped = np.clip(X_train_raw, lo, hi)
            mean = np.nanmean(clipped, axis=0)
            std = np.nanstd(clipped, ddof=1, axis=0)
            std = np.where(std < 1e-10, 1.0, std)

            X_train = (clipped - mean) / std
            X_train = np.nan_to_num(X_train, nan=0.0)

            # 预测集预处理（用训练集统计量）
            X_pred_raw = pred_data.select(fs_factors).to_numpy()
            X_pred = np.clip(X_pred_raw, lo, hi)
            X_pred = (X_pred - mean) / std
            X_pred = np.nan_to_num(X_pred, nan=0.0)

            y_train = train_data["label"].to_numpy()
            valid_mask = ~np.isnan(y_train)
            X_train = X_train[valid_mask]
            y_train = y_train[valid_mask]

            preprocessed[(fs_name, window)] = (X_train, y_train, X_pred)

        if not preprocessed:
            logger.warning(f"{rebalance_date}: 无有效预处理组，跳过")
            return {"date": rebalance_date, "selected_codes": [], "predictions": {}}

        # 4. 混合并行训练: Phase 1 LGB/XGB(threading并行) + Phase 2 RF/ET(n_jobs串行)
        # need_ic: 仅IC-based集成方法(ic_weighted/ic_rank_weighted)需要holdout计算OOF IC
        # rank_average/equal_weight全量训练, 避免浪费数据
        need_ic = self.ensemble_method in ("ic_weighted", "ic_rank_weighted")

        boost_tasks = []  # LGB/XGB: 释放GIL, threading可真并行
        tree_tasks = []   # RF/ET: 每模型用n_jobs核
        for expert in self.experts:
            key = (expert.feature_set, expert.train_window)
            if key not in preprocessed:
                continue
            X_train, y_train, X_pred = preprocessed[key]
            if expert.model_type in ("lgb", "xgb"):
                boost_tasks.append((expert, X_train, y_train, X_pred))
            else:
                tree_tasks.append((expert, X_train, y_train, X_pred))

        # Phase 1: LGB/XGB并行训练 (threading, 释放GIL)
        # n_jobs=-1时全量并行; 并行模式下cap到self.n_jobs
        boost_parallel = len(boost_tasks) if self.n_jobs <= 0 else min(len(boost_tasks), self.n_jobs)
        boost_results = Parallel(
            n_jobs=boost_parallel, backend="threading", verbose=0
        )(
            delayed(train_one_expert)(exp, X_tr, y_tr, X_pr, 1, 0.2, need_ic)
            for exp, X_tr, y_tr, X_pr in boost_tasks
        ) if boost_tasks else []

        # Phase 2: RF/ET串行训练 (每模型n_jobs=self.n_jobs核建树)
        tree_results = []
        for exp, X_tr, y_tr, X_pr in tree_tasks:
            tree_results.append(train_one_expert(exp, X_tr, y_tr, X_pr, self.n_jobs, 0.2, need_ic))

        # 合并预测结果: 每个专家返回 (val_preds, val_labels, final_preds)
        all_tasks = boost_tasks + tree_tasks
        all_results = list(boost_results) + tree_results

        # 5. 存储专家预测 + 计算OOS IC权重(80/20 holdout)
        pred_codes = pred_data["code"].to_list()
        expert_predictions = []
        for (exp, _, _, _), (val_preds, val_labels, preds) in zip(all_tasks, all_results):
            ic = self._compute_oof_ic(val_preds, val_labels)
            expert_predictions.append({
                "expert_id": exp.expert_id,
                "model_type": exp.model_type,
                "predictions": dict(zip(pred_codes, preds.tolist())),
                "ic": ic,
            })

        # 6. 集成
        if self.ensemble_method == "ic_weighted":
            composite_scores = self._ensemble_ic_weighted(expert_predictions, pred_codes)
        elif self.ensemble_method == "rank_average":
            composite_scores = self._ensemble_rank_average(expert_predictions, pred_codes)
        elif self.ensemble_method == "ic_rank_weighted":
            composite_scores = self._ensemble_ic_rank_weighted(expert_predictions, pred_codes)
        else:
            composite_scores = self._ensemble_equal_weight(expert_predictions, pred_codes)

        # 7. 选Top-N
        sorted_codes = sorted(composite_scores.items(), key=lambda x: x[1], reverse=True)
        selected = [c for c, s in sorted_codes[:self.top_n] if not np.isnan(s)]

        return {
            "date": rebalance_date,
            "selected_codes": selected,
            "predictions": composite_scores,
            "expert_predictions": expert_predictions,
        }

    def _ensemble_equal_weight(
        self, expert_predictions: list[dict], codes: list[str]
    ) -> dict[str, float]:
        """等权平均集成"""
        scores = {code: [] for code in codes}
        for exp in expert_predictions:
            for code, pred in exp["predictions"].items():
                if code in scores and not np.isnan(pred):
                    scores[code].append(pred)

        composite = {}
        for code, preds in scores.items():
            if len(preds) > 0:
                composite[code] = float(np.mean(preds))
            else:
                composite[code] = 0.0
        return composite

    def _compute_oof_ic(self, val_preds: np.ndarray, val_labels: np.ndarray) -> float:
        """计算OOS Spearman IC (基于80/20 holdout验证集)

        相比旧版样本内IC, 这是真实泛化IC估计:
        - 旧版: model.predict(X_train) vs y_train → 深树in-sample IC虚高 → 过拟合
        - 新版: model.predict(X_val) vs y_val (val未参与训练) → 真实IC

        Returns:
            IC值, 范围[-1, 1]. 负IC表示反向预测能力
        """
        try:
            from scipy.stats import spearmanr
            if len(val_labels) < 10:
                return 0.0
            valid = ~np.isnan(val_preds) & ~np.isnan(val_labels)
            if valid.sum() < 10:
                return 0.0
            ic, _ = spearmanr(val_preds[valid], val_labels[valid])
            if np.isnan(ic):
                return 0.0
            return float(ic)
        except Exception:
            return 0.0

    def _ensemble_ic_weighted(
        self, expert_predictions: list[dict], codes: list[str]
    ) -> dict[str, float]:
        """IC加权集成 - 用各专家近期IC作为权重

        权重 = max(IC, 0), 负IC专家不参与投票
        """
        # 计算各专家权重
        weights = {}
        for exp in expert_predictions:
            ic = exp.get("ic", 0.0)
            weights[exp["expert_id"]] = max(0.0, ic)

        total_weight = sum(weights.values())
        if total_weight < 1e-8:
            # 所有IC都为0或负, 退化为等权
            return self._ensemble_equal_weight(expert_predictions, codes)

        scores = {code: 0.0 for code in codes}
        for exp in expert_predictions:
            w = weights.get(exp["expert_id"], 0.0)
            if w < 1e-8:
                continue
            for code, pred in exp["predictions"].items():
                if code in scores and not np.isnan(pred):
                    scores[code] += w * pred

        for code in scores:
            scores[code] /= total_weight
        return scores

    def _ensemble_rank_average(
        self, expert_predictions: list[dict], codes: list[str]
    ) -> dict[str, float]:
        """Rank平均集成 - 对每个专家的预测排名后取平均

        更鲁棒, 不受异常值影响
        """
        from scipy.stats import rankdata
        scores = {code: [] for code in codes}
        for exp in expert_predictions:
            preds = exp["predictions"]
            valid = [(c, preds[c]) for c in codes if c in preds and not np.isnan(preds[c])]
            if len(valid) < 2:
                continue
            values = [v for _, v in valid]
            ranks = rankdata(values) / len(values)  # 归一化到[0, 1]
            for (c, _), r in zip(valid, ranks):
                scores[c].append(r)

        composite = {}
        for code, ranks in scores.items():
            if len(ranks) > 0:
                composite[code] = float(np.mean(ranks))
            else:
                composite[code] = 0.0
        return composite

    def _ensemble_ic_rank_weighted(
        self, expert_predictions: list[dict], codes: list[str]
    ) -> dict[str, float]:
        """IC加权Rank集成 - rank平均 + IC加权

        结合rank的鲁棒性和IC加权的自适应性
        """
        from scipy.stats import rankdata
        # 计算各专家权重
        weights = {}
        for exp in expert_predictions:
            ic = exp.get("ic", 0.0)
            weights[exp["expert_id"]] = max(0.0, ic)

        total_weight = sum(weights.values())
        if total_weight < 1e-8:
            return self._ensemble_rank_average(expert_predictions, codes)

        scores = {code: 0.0 for code in codes}
        for exp in expert_predictions:
            w = weights.get(exp["expert_id"], 0.0)
            if w < 1e-8:
                continue
            preds = exp["predictions"]
            valid = [(c, preds[c]) for c in codes if c in preds and not np.isnan(preds[c])]
            if len(valid) < 2:
                continue
            values = [v for _, v in valid]
            ranks = rankdata(values) / len(values)
            for (c, _), r in zip(valid, ranks):
                scores[c] += w * r

        for code in scores:
            scores[code] /= total_weight
        return scores
