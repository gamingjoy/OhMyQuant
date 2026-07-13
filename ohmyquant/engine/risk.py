"""风控管理器基类

可插拔风控接口，参考 halo_index 的 RiskManager。
所有风控插件实现此接口，通过统一 register_risk_manager 装饰器注册。

配置中通过 risk.method 切换:
  method: vol_target      → VolTargetRiskManager
  method: cvar            → CVaRRiskManager
  method: drawdown        → DrawdownDefenseRiskManager
  method: regime_adaptive → RegimeAdaptiveRiskManager（默认，最全面）
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import polars as pl

from ..core.types import Regime

TRADING_DAYS = 242

REGIME_STRONG_TREND = "strong_trend"
REGIME_WEAK_TREND = "weak_trend"
REGIME_SIDEWAY = "sideway"
REGIME_HIGH_VOL = "high_vol"


class BaseRiskManager(ABC):
    """风控管理器抽象基类

    子类实现 compute_exposure() 和 detect_regime() 方法，
    根据历史净值和收益序列计算当日有效暴露度和市场状态。
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.target_vol: float = cfg.get("target_vol", 0.25)
        self.lookback: int = cfg.get("lookback", 60)
        self.min_exposure_scale: float = cfg.get("min_exposure_scale", 0.5)
        self.var_threshold: float = cfg.get("var_threshold", -0.03)
        self.cvar_limit_factor: float = cfg.get("cvar_limit_factor", 1.5)
        self.cvar_penalty_strength: float = cfg.get("cvar_penalty_strength", 0.5)
        self.vol_trend_mode: str = cfg.get("vol_trend_mode", "managed_vol")
        self.vol_trend_strength: float = cfg.get("vol_trend_strength", 2.0)
        self.corr_risk_strength: float = cfg.get("corr_risk_strength", 0.5)
        self.tail_risk_strength: float = cfg.get("tail_risk_strength", 0.3)

    @abstractmethod
    def compute_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
        current_exposure: float,
        **kwargs,
    ) -> tuple[float, Regime]:
        """计算当日有效暴露度

        Args:
            nav: 净值序列（polars Series）
            daily_returns: 日收益序列（polars Series）
            current_idx: 当前时间索引
            current_exposure: 当前暴露度
            **kwargs: 额外参数（如 ic_df, strong_factors 等供高级风控使用）

        Returns:
            (effective_scale, regime)
            effective_scale: 有效暴露度，通常在 [0, 1.5] 之间
            regime: 市场状态
        """
        ...

    @abstractmethod
    def detect_regime(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        lookback: int | None = None,
    ) -> tuple[Regime, float]:
        """检测市场状态

        Args:
            daily_returns: 日收益序列
            current_idx: 当前时间索引
            lookback: 回看窗口，None 则用 self.lookback

        Returns:
            (regime, confidence)
            regime: strong_trend / weak_trend / sideway / high_vol
            confidence: 置信度 [0, 1]
        """
        ...

    # ------------------------------------------------------------------
    # 共享工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _slice(daily_returns: pl.Series, current_idx: int, lookback: int) -> np.ndarray:
        """安全切片：取 [max(0, current_idx-lookback), current_idx) 的收益数组"""
        start = max(0, current_idx - lookback)
        return daily_returns.to_numpy()[start:current_idx]

    @staticmethod
    def _annualized_vol(daily_returns_slice: np.ndarray, trading_days: int = TRADING_DAYS) -> float:
        """计算年化波动率"""
        if len(daily_returns_slice) < 2:
            return 0.0
        std = float(np.std(daily_returns_slice, ddof=1))
        return std * np.sqrt(trading_days)

    @staticmethod
    def _compute_cvar(daily_returns_slice: np.ndarray, alpha: float = 0.05) -> float:
        """计算 CVaR（条件风险价值，尾部均值）

        Args:
            daily_returns_slice: 日收益数组
            alpha: 尾部比例（0.05 表示最差的 5%）

        Returns:
            CVaR 值（负数）
        """
        if len(daily_returns_slice) < 10:
            return float(np.mean(daily_returns_slice)) if len(daily_returns_slice) > 0 else 0.0
        sorted_ret = np.sort(daily_returns_slice)
        n_tail = max(int(len(sorted_ret) * alpha), 5)
        return float(np.mean(sorted_ret[:n_tail]))

    @staticmethod
    def _compute_var(daily_returns_slice: np.ndarray, alpha: float = 0.05) -> float:
        """计算 VaR（风险价值）"""
        if len(daily_returns_slice) < 10:
            return 0.0
        return float(np.quantile(daily_returns_slice, alpha))

    @staticmethod
    def _compute_drawdown(nav: pl.Series, current_idx: int) -> float:
        """计算当前回撤（负数或0）

        Returns:
            回撤值，如 -0.10 表示回撤 10%
        """
        if current_idx < 1:
            return 0.0
        nav_arr = nav.to_numpy()[: current_idx + 1]
        if len(nav_arr) == 0:
            return 0.0
        cummax = np.maximum.accumulate(nav_arr)
        current = nav_arr[-1]
        peak = cummax[-1]
        if peak <= 0:
            return 0.0
        return float((current - peak) / peak)

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        """numpy.clip 的标量版"""
        return float(max(low, min(high, value)))


__all__ = [
    "BaseRiskManager",
    "TRADING_DAYS",
    "REGIME_STRONG_TREND",
    "REGIME_WEAK_TREND",
    "REGIME_SIDEWAY",
    "REGIME_HIGH_VOL",
]
