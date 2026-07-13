"""混合选股器

ICIR 初筛 + 可选 ML 重排。
当 LightGBM 不可用时自动降级为纯 ICIR。
"""
from __future__ import annotations

from typing import Any

import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ..selector import BaseSelector
from .icir_selector import ICIRSelector

logger = get_logger(__name__)


@register_selector("hybrid")
class HybridSelector(BaseSelector):
    """ICIR + ML 混合选股器

    流程:
      1. ICIR 选出候选池（top_n × candidate_mult）
      2. ML 在候选池内重排（若可用）
      3. ML 不可用时降级为纯 ICIR
      4. Regime 自适应：趋势市给 ML 更多权重
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        hybrid_cfg = self.config.get("hybrid", {})
        self.candidate_mult = hybrid_cfg.get("icir_candidate_mult", 2.0)
        self.regime_adjust = hybrid_cfg.get("regime_adjust", True)
        self.trend_ml_weight = hybrid_cfg.get("trend_ml_weight", 0.35)
        self.sideways_ml_weight = hybrid_cfg.get("sideways_ml_weight", 0.10)

        self.icir_selector = ICIRSelector(config)
        self._ml_selector = None

        # 尝试加载 ML 选股器
        try:
            from .ml_selector import MLSelector

            self._ml_selector = MLSelector(config)
        except ImportError:
            logger.info("LightGBM 未安装，HybridSelector 将使用纯 ICIR 模式")

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        # Step 1: ICIR 选出候选池（扩大范围）
        candidate_n = int(self.top_n * self.candidate_mult)
        original_top_n = self.icir_selector.top_n
        self.icir_selector.top_n = candidate_n
        icir_weights = self.icir_selector.select(
            factors, ic_df, stock_codes, current_idx, close,
            regime=regime, strong_factors=strong_factors,
        )
        self.icir_selector.top_n = original_top_n

        if icir_weights is None:
            return None

        # Step 2: ML 重排（若可用）
        if self._ml_selector is not None:
            ml_weights = self._ml_selector.select(
                factors, ic_df, stock_codes, current_idx, close,
                regime=regime, strong_factors=strong_factors,
                fwd_returns=kwargs.get("fwd_returns"),
            )

            if ml_weights is not None:
                return self._blend(icir_weights, ml_weights, regime)

        # ML 不可用，截断到 top_n
        if self.top_n < len(icir_weights):
            sorted_w = sorted(icir_weights.items(), key=lambda x: x[1], reverse=True)
            top = sorted_w[: self.top_n]
            total = sum(w for _, w in top)
            return {code: w / total for code, w in top}

        return icir_weights

    def _blend(
        self,
        icir_weights: dict[str, float],
        ml_weights: dict[str, float],
        regime: str | None,
    ) -> dict[str, float]:
        """混合 ICIR 和 ML 分数"""
        # 确定混合权重
        ml_w = 0.35
        if self.regime_adjust and regime:
            if regime in ("strong_trend", "weak_trend"):
                ml_w = self.trend_ml_weight
            elif regime == "sideway":
                ml_w = self.sideways_ml_weight
        icir_w = 1.0 - ml_w

        # 在 ICIR 候选池内混合
        candidates = list(icir_weights.keys())
        ml_in_candidates = {c: ml_weights.get(c, 0) for c in candidates}

        # 归一化到 [0,1]
        max_icir = max(icir_weights.values()) if icir_weights else 1
        max_ml = max(ml_in_candidates.values()) if ml_in_candidates else 1

        blended = {}
        for code in candidates:
            icir_norm = icir_weights[code] / max_icir if max_icir > 0 else 0
            ml_norm = ml_in_candidates[code] / max_ml if max_ml > 0 else 0
            blended[code] = icir_w * icir_norm + ml_w * ml_norm

        # 过滤正权重
        blended = {k: v for k, v in blended.items() if v > 0}

        # 取 Top-N
        if self.top_n < len(blended):
            sorted_b = sorted(blended.items(), key=lambda x: x[1], reverse=True)
            blended = dict(sorted_b[: self.top_n])

        # 归一化
        total = sum(blended.values())
        if total > 0:
            blended = {k: v / total for k, v in blended.items()}

        return self.apply_weight_cap(blended)

    def select_strong_factors(self, ic_df: pl.DataFrame, train_end: str) -> list[str]:
        return self.icir_selector.select_strong_factors(ic_df, train_end)


@register_selector("adaptive")
class AdaptiveICIRSelector(ICIRSelector):
    """自适应 ICIR 选股器

    在 ICIR 基础上做自适应微调:
      1. 因子 IC 衰减检测
      2. 因子动量增强
      3. 回撤自适应
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        adaptive_cfg = self.config.get("adaptive", {})
        self.ic_decay_detect_window = adaptive_cfg.get("ic_decay_detect_window", 40)
        self.ic_decay_penalty = adaptive_cfg.get("ic_decay_penalty", 0.5)
        self.factor_momentum_window = adaptive_cfg.get("factor_momentum_window", 20)
        self.factor_momentum_up = adaptive_cfg.get("factor_momentum_up", 1.2)
        self.factor_momentum_down = adaptive_cfg.get("factor_momentum_down", 0.8)

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        # 先用基础 ICIR 选股
        base_weights = super().select(
            factors, ic_df, stock_codes, current_idx, close,
            regime=regime, strong_factors=strong_factors,
        )
        if base_weights is None:
            return None

        # 计算因子自适应调整系数
        factor_adj = self._compute_factor_adjustments(ic_df, strong_factors or [], current_idx)

        # 微调权重
        adjusted = self._adjust_weights(base_weights, factors, factor_adj, current_idx)
        return adjusted

    def _compute_factor_adjustments(
        self, ic_df: pl.DataFrame, factor_names: list[str], current_idx: int
    ) -> dict[str, float]:
        """计算因子调整系数"""
        adjustments = {}
        for fname in factor_names:
            if fname not in ic_df.columns:
                adjustments[fname] = 1.0
                continue

            ic_series = ic_df[fname][max(0, current_idx - 60) : current_idx].drop_nulls()
            if len(ic_series) < 20:
                adjustments[fname] = 1.0
                continue

            ic_vals = ic_series.to_numpy()
            adj = 1.0

            # IC 衰减检测
            if len(ic_vals) >= self.ic_decay_detect_window:
                half = self.ic_decay_detect_window // 2
                recent = np.mean(ic_vals[-half:])
                older = np.mean(ic_vals[-self.ic_decay_detect_window : -half])
                if abs(older) > 1e-6:
                    change = (recent - older) / abs(older)
                    if change < -0.3:
                        adj *= self.ic_decay_penalty

            # 因子动量
            if len(ic_vals) >= self.factor_momentum_window * 2:
                w = self.factor_momentum_window
                recent = np.mean(ic_vals[-w:])
                older = np.mean(ic_vals[-2 * w : -w])
                if abs(older) > 1e-6:
                    momentum = (recent - older) / abs(older)
                    if momentum > 0.2:
                        adj *= self.factor_momentum_up
                    elif momentum < -0.2:
                        adj *= self.factor_momentum_down

            adjustments[fname] = adj
        return adjustments

    def _adjust_weights(
        self,
        base_weights: dict[str, float],
        factors: dict[str, pl.DataFrame],
        factor_adj: dict[str, float],
        current_idx: int,
    ) -> dict[str, float]:
        """对权重做自适应微调"""
        selected = list(base_weights.keys())
        stock_adj = {code: 1.0 for code in selected}

        for fname, adj in factor_adj.items():
            if adj == 1.0 or fname not in factors:
                continue
            factor_df = factors[fname]
            if current_idx >= len(factor_df):
                continue

            row = factor_df.row(current_idx, named=True)
            vals = {}
            for code in selected:
                if code in row and row[code] is not None:
                    v = row[code]
                    if isinstance(v, (int, float)):
                        vals[code] = float(v)

            if len(vals) < 2:
                continue

            # 排名
            sorted_vals = sorted(vals.items(), key=lambda x: x[1])
            n = len(sorted_vals)
            for rank_idx, (code, _) in enumerate(sorted_vals):
                pct = (rank_idx + 1) / n
                if adj > 1.0:
                    stock_adj[code] += pct * (adj - 1.0)
                else:
                    stock_adj[code] -= pct * (1.0 - adj)

        # 应用调整（clip 到 [0.3, 1.7]）
        adjusted = {}
        for code in selected:
            scale = max(0.3, min(1.7, stock_adj[code]))
            adjusted[code] = base_weights[code] * scale

        # 归一化
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}
        return adjusted


__all__ = ["HybridSelector", "AdaptiveICIRSelector"]
