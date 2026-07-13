"""多策略集成

将多个策略的日收益序列按权重组合，输出集成净值与绩效。

权重方式：
  - equal_weight: 等权 1/N
  - perf_weight:  按 Sharpe 加权（w_i ∝ max(sharpe_i, 0)，全 ≤0 退化为等权）
  - ir_weight:    按信息比率加权（需 benchmark_returns，缺失则退化 perf_weight）

收益对齐：取各成分日期交集，缺失日按 0 填充（假设该日无持仓）。

Usage:
    # 方式 1: 从已保存的结果文件加载（推荐，避免重跑回测）
    ens = StrategyEnsemble.from_results(
        weighting="perf_weight",
        result_files=["output/ycj_v1/results.json", "output/etf_v1/results.json"],
    )
    result = ens.run_from_results()
    print(result.metrics.sharpe_ratio)

    # 方式 2: 重新运行回测（耗时较长）
    ens = StrategyEnsemble(weighting="perf_weight")
    ens.add_strategy("ycj", "v1")
    ens.add_strategy("etf", "v1")
    result = ens.run()
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..analysis.metrics import (
    PerformanceMetrics,
    compute_info_ratio,
    compute_metrics,
    compute_sharpe_ratio,
)
from ..core.logging import get_logger
from ..strategy.runner import StrategyResult, StrategyRunner

logger = get_logger(__name__)

VALID_WEIGHTING = ("equal", "perf_weight", "ir_weight")


def _returns_to_array(daily_returns) -> np.ndarray:
    if daily_returns is None:
        return np.array([])
    if hasattr(daily_returns, "to_numpy"):
        return daily_returns.to_numpy()
    return np.asarray(daily_returns)


@dataclass
class EnsembleResult:
    """集成结果"""

    weighting: str
    nav: list[float]
    dates: list[str]
    metrics: PerformanceMetrics
    constituents: list[dict] = field(default_factory=list)


class StrategyEnsemble:
    """多策略集成

    Args:
        weighting: 加权方式（equal/perf_weight/ir_weight）
        benchmark_returns: 基准日收益（ir_weight 必需），numpy array 或 list
    """

    def __init__(
        self,
        weighting: str = "equal",
        benchmark_returns: np.ndarray | list[float] | None = None,
    ):
        if weighting not in VALID_WEIGHTING:
            raise ValueError(f"未知加权方式: {weighting}，可选 {VALID_WEIGHTING}")
        self.weighting = weighting
        self.benchmark_returns = (
            np.asarray(benchmark_returns) if benchmark_returns is not None else None
        )
        self._strategies: list[tuple[str, str, float]] = []
        self._loaded: list[tuple[str, np.ndarray, list[str]]] = []

    def add_strategy(
        self, strategy_type: str, version: str, weight: float = 1.0
    ) -> "StrategyEnsemble":
        """添加成分策略

        Args:
            strategy_type: 策略类型
            version: 版本号
            weight: 初始权重（equal 模式忽略，perf/ir 模式作为先验乘子）
        """
        self._strategies.append((strategy_type, version, weight))
        return self

    @classmethod
    def from_results(
        cls,
        result_files: list[str],
        weighting: str = "equal",
        benchmark_returns: np.ndarray | list[float] | None = None,
    ) -> "StrategyEnsemble":
        """从已保存的 results.json 文件加载策略收益序列

        避免重新运行回测，适合快速试验不同加权方式。

        Args:
            result_files: results.json 文件路径列表
            weighting: 加权方式
            benchmark_returns: 基准收益（ir_weight 用）
        """
        ens = cls(weighting=weighting, benchmark_returns=benchmark_returns)
        for path in result_files:
            if not os.path.exists(path):
                raise FileNotFoundError(f"结果文件不存在: {path}")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = f"{data.get('strategy_type', data.get('strategy', '?'))}_{data.get('version', '?')}"
            returns = np.array(data.get("daily_returns", []))
            dates = data.get("dates", [])
            if len(returns) == 0:
                logger.warning(f"结果文件 {path} 缺少 daily_returns，跳过")
                continue
            ens._loaded.append((name, returns, dates))
            logger.info(f"加载策略结果: {name} ({len(returns)} 天)")
        return ens

    def _run_constituents(
        self, config_overrides: dict[str, Any] | None
    ) -> list[tuple[str, str, StrategyResult, np.ndarray, list[str]]]:
        """运行所有成分策略

        Returns:
            [(type, version, result, returns_array, dates), ...]
        """
        constituents = []
        for stype, version, _ in self._strategies:
            logger.info(f"运行成分策略: {stype} {version}")
            result = StrategyRunner.run_strategy(stype, version, config_overrides)
            returns = _returns_to_array(result.backtest_result.daily_returns)
            dates = result.backtest_result.dates
            constituents.append((stype, version, result, returns, dates))
        return constituents

    def _compute_weights(
        self,
        constituents: list[tuple[str, str, StrategyResult, np.ndarray, list[str]]],
    ) -> np.ndarray:
        """计算成分权重"""
        n = len(constituents)
        if n == 0:
            return np.array([])

        if self.weighting == "equal":
            return np.ones(n) / n

        # perf_weight / ir_weight
        scores = np.zeros(n)
        for i, (_, _, _, returns, dates) in enumerate(constituents):
            if self.weighting == "ir_weight" and self.benchmark_returns is not None:
                bench = self.benchmark_returns
                # 对齐长度
                m = min(len(returns), len(bench))
                if m > 1:
                    scores[i] = max(compute_info_ratio(returns[:m], bench[:m]), 0.0)
                else:
                    scores[i] = 0.0
            else:
                if self.weighting == "ir_weight" and self.benchmark_returns is None:
                    logger.warning(
                        "ir_weight 需要 benchmark_returns，缺失，退化为 perf_weight"
                    )
                scores[i] = max(compute_sharpe_ratio(returns), 0.0)

        total = scores.sum()
        if total <= 0:
            logger.info("所有成分 Sharpe/IR ≤ 0，退化为等权")
            return np.ones(n) / n
        return scores / total

    def _align_returns(
        self,
        constituents: list[tuple[str, str, StrategyResult, np.ndarray, list[str]]],
    ) -> tuple[list[str], list[np.ndarray]]:
        """按日期交集对齐各成分收益

        Returns:
            (common_dates, [returns_array_aligned, ...])
        """
        if not constituents:
            return [], []

        # 取日期交集
        common = set(constituents[0][4])
        for _, _, _, _, dates in constituents[1:]:
            common &= set(dates)
        common_dates = sorted(common)
        if not common_dates:
            logger.warning("各成分策略无公共交易日")
            return [], []

        # 对每个成分构建 date->return 映射，按 common_dates 取值（缺失填 0）
        aligned: list[np.ndarray] = []
        for _, _, _, returns, dates in constituents:
            d2r = dict(zip(dates, returns.tolist() if hasattr(returns, "tolist") else list(returns)))
            aligned.append(np.array([d2r.get(d, 0.0) for d in common_dates]))
        return common_dates, aligned

    def run(
        self, config_overrides: dict[str, Any] | None = None
    ) -> EnsembleResult:
        """运行集成

        Args:
            config_overrides: 传递给各成分策略的配置覆盖

        Returns:
            EnsembleResult
        """
        if not self._strategies:
            raise ValueError("未添加任何成分策略")

        logger.info(
            f"开始集成: {len(self._strategies)} 个策略, weighting={self.weighting}"
        )

        constituents = self._run_constituents(config_overrides)
        weights = self._compute_weights(constituents)
        common_dates, aligned = self._align_returns(constituents)

        if not common_dates:
            return EnsembleResult(
                weighting=self.weighting,
                nav=[1.0],
                dates=[],
                metrics=PerformanceMetrics(),
                constituents=[],
            )

        # 加权组合收益
        combined = np.zeros(len(common_dates))
        for w, ret in zip(weights, aligned):
            combined += w * ret

        # 净值（归一化起点 1.0）
        nav = np.cumprod(1.0 + combined)
        nav_list = nav.tolist()

        metrics = compute_metrics(combined)

        # 成分明细
        constituent_info = []
        for (stype, version, _, returns, dates), w in zip(constituents, weights):
            constituent_info.append(
                {
                    "strategy_type": stype,
                    "version": version,
                    "weight": float(w),
                    "sharpe": compute_sharpe_ratio(returns),
                    "n_days": len(dates),
                }
            )

        logger.info(
            f"集成完成: {len(common_dates)} 天, "
            f"combined_sharpe={metrics.sharpe_ratio:.4f}, "
            f"weights={[round(w, 3) for w in weights]}"
        )

        return EnsembleResult(
            weighting=self.weighting,
            nav=nav_list,
            dates=common_dates,
            metrics=metrics,
            constituents=constituent_info,
        )

    def run_from_results(self) -> EnsembleResult:
        """从已加载的结果文件运行集成（不重跑回测）

        需先通过 from_results() 类方法创建实例。

        Returns:
            EnsembleResult
        """
        if not self._loaded:
            raise ValueError("未加载任何结果文件，请使用 from_results() 创建实例")

        logger.info(
            f"开始集成（从结果文件）: {len(self._loaded)} 个策略, weighting={self.weighting}"
        )

        # 计算权重（直接用 returns，不需要完整 constituent 格式）
        n = len(self._loaded)
        if self.weighting == "equal":
            weights = np.ones(n) / n
        else:
            scores = np.zeros(n)
            for i, (_, returns, _) in enumerate(self._loaded):
                if self.weighting == "ir_weight" and self.benchmark_returns is not None:
                    bench = self.benchmark_returns
                    m = min(len(returns), len(bench))
                    if m > 1:
                        scores[i] = max(compute_info_ratio(returns[:m], bench[:m]), 0.0)
                    else:
                        scores[i] = 0.0
                else:
                    scores[i] = max(compute_sharpe_ratio(returns), 0.0)
            total = scores.sum()
            if total <= 0:
                logger.info("所有成分 Sharpe/IR ≤ 0，退化为等权")
                weights = np.ones(n) / n
            else:
                weights = scores / total

        # 对齐收益：有 dates 用日期交集，无 dates 用索引对齐（截断到最短）
        has_dates = all(len(d) > 0 for _, _, d in self._loaded)
        if has_dates:
            common = set(self._loaded[0][2])
            for _, _, dates in self._loaded[1:]:
                common &= set(dates)
            common_dates = sorted(common)
            aligned = []
            for _, returns, dates in self._loaded:
                d2r = dict(zip(dates, returns.tolist() if hasattr(returns, "tolist") else list(returns)))
                aligned.append(np.array([d2r.get(d, 0.0) for d in common_dates]))
        else:
            min_len = min(len(r) for _, r, _ in self._loaded)
            common_dates = [str(i) for i in range(min_len)]
            aligned = [r[:min_len] for _, r, _ in self._loaded]

        if not common_dates:
            return EnsembleResult(
                weighting=self.weighting,
                nav=[1.0],
                dates=[],
                metrics=PerformanceMetrics(),
                constituents=[],
            )

        combined = np.zeros(len(common_dates))
        for w, ret in zip(weights, aligned):
            combined += w * ret

        nav = np.cumprod(1.0 + combined)
        nav_list = nav.tolist()

        metrics = compute_metrics(combined)

        constituent_info = []
        for (name, returns, dates), w in zip(self._loaded, weights):
            constituent_info.append(
                {
                    "strategy": name,
                    "weight": float(w),
                    "sharpe": compute_sharpe_ratio(returns),
                    "n_days": len(dates) if dates else len(returns),
                }
            )

        logger.info(
            f"集成完成: {len(common_dates)} 天, "
            f"combined_sharpe={metrics.sharpe_ratio:.4f}, "
            f"weights={[round(w, 3) for w in weights]}"
        )

        return EnsembleResult(
            weighting=self.weighting,
            nav=nav_list,
            dates=common_dates,
            metrics=metrics,
            constituents=constituent_info,
        )


__all__ = [
    "StrategyEnsemble",
    "EnsembleResult",
]
