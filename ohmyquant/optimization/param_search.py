"""参数搜索

基于 Optuna 的策略超参搜索；Optuna 不可用时降级为网格搜索。

支持扁平参数路径（如 "selection.top_n"），自动深合并到策略 yaml 基础配置。
param_space 每项规格：
  - {"type": "int", "low": 10, "high": 100, "step": 10}
  - {"type": "float", "low": 0.1, "high": 0.4, "step": 0.05}   # 网格用 step；optuna 用 log 可选
  - {"type": "float", "low": 0.1, "high": 0.4, "log": True}
  - {"type": "categorical", "choices": ["monthly", "weekly"]}

Usage:
    ps = ParamSearcher(n_trials=20, metric="sharpe")
    report = ps.search("ycj", "v1", {
        "selection.top_n": {"type": "int", "low": 20, "high": 80, "step": 20},
        "risk.target_vol": {"type": "float", "low": 0.15, "high": 0.35, "step": 0.1},
    })
    print(report.summary())
"""
from __future__ import annotations

import copy
import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np

from ..analysis.metrics import (
    compute_max_drawdown,
    compute_sharpe_ratio,
    compute_total_return,
)
from ..core.logging import get_logger
from ..strategy.runner import StrategyResult, StrategyRunner
from ..strategy.version_manager import VersionManager

logger = get_logger(__name__)

try:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _HAS_OPTUNA = True
except ImportError:
    _HAS_OPTUNA = False
    logger.info("optuna 未安装，ParamSearcher 将降级为网格搜索")


def _apply_flat_params(base: dict, flat_params: dict[str, Any]) -> dict:
    """将扁平参数（"a.b.c" -> value）深合并进基础配置的嵌套 dict

    Args:
        base: 基础配置（来自 yaml）
        flat_params: {"selection.top_n": 20, "risk.target_vol": 0.2}

    Returns:
        深合并后的完整配置 dict
    """
    result = copy.deepcopy(base)
    for path, val in flat_params.items():
        keys = path.split(".")
        d = result
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = val
    return result


def _returns_to_array(daily_returns) -> np.ndarray:
    if daily_returns is None:
        return np.array([])
    if hasattr(daily_returns, "to_numpy"):
        return daily_returns.to_numpy()
    return np.asarray(daily_returns)


@dataclass
class TrialResult:
    """单次试验结果"""

    params: dict[str, Any]
    value: float
    metrics: dict[str, float]


@dataclass
class OptimizationReport:
    """参数搜索报告"""

    strategy_type: str
    version: str
    metric: str
    backend: str  # "optuna" / "grid"
    best_params: dict[str, Any] = field(default_factory=dict)
    best_value: float = 0.0
    best_metrics: dict[str, float] = field(default_factory=dict)
    n_trials: int = 0
    trials: list[TrialResult] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"参数搜索报告: {self.strategy_type} {self.version}",
            f"后端: {self.backend}  试验数: {self.n_trials}  指标: {self.metric}",
            "-" * 60,
            f"最优值: {self.best_value:.4f}",
            "最优参数:",
        ]
        for k, v in self.best_params.items():
            lines.append(f"  {k} = {v}")
        lines.append("-" * 60)
        lines.append("Top-5 试验:")
        sorted_trials = sorted(self.trials, key=lambda t: t.value, reverse=True)[:5]
        for i, t in enumerate(sorted_trials):
            lines.append(
                f"  [{i+1}] value={t.value:.4f}  sharpe={t.metrics.get('sharpe', 0):.4f}  "
                f"params={t.params}"
            )
        lines.append("=" * 60)
        return "\n".join(lines)


class ParamSearcher:
    """参数搜索器

    Args:
        n_trials: 最大试验数
        metric: 优化指标（sharpe / total_return / max_drawdown）
        direction: "maximize" 或 "minimize"
    """

    _METRIC_FUNCS = {
        "sharpe": compute_sharpe_ratio,
        "total_return": compute_total_return,
    }

    def __init__(
        self,
        n_trials: int = 50,
        metric: str = "sharpe",
        direction: str = "maximize",
    ):
        if metric not in ("sharpe", "total_return", "max_drawdown"):
            raise ValueError(f"不支持指标: {metric}，可选 sharpe/total_return/max_drawdown")
        self.n_trials = n_trials
        self.metric = metric
        self.direction = direction

    def _metric_value(self, returns: np.ndarray) -> float:
        if len(returns) == 0:
            return 0.0
        if self.metric == "max_drawdown":
            dd, _ = compute_max_drawdown(returns)
            return dd  # 负值；maximize 时越大（越接近0）越好
        return self._METRIC_FUNCS[self.metric](returns)

    def _metrics_dict(self, returns: np.ndarray) -> dict[str, float]:
        if len(returns) == 0:
            return {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0}
        dd, _ = compute_max_drawdown(returns)
        return {
            "sharpe": compute_sharpe_ratio(returns),
            "total_return": compute_total_return(returns),
            "max_drawdown": float(dd),
        }

    def _evaluate(
        self,
        strategy_type: str,
        version: str,
        flat_params: dict[str, Any],
        base_config: dict,
    ) -> tuple[float, dict[str, float]]:
        """评估单组参数

        Returns:
            (objective_value, metrics_dict)
        """
        merged_config = _apply_flat_params(base_config, flat_params)
        result: StrategyResult = StrategyRunner.run_strategy(
            strategy_type, version, merged_config
        )
        returns = _returns_to_array(result.backtest_result.daily_returns)
        value = self._metric_value(returns)
        metrics = self._metrics_dict(returns)
        return value, metrics

    def _grid(self, param_space: dict[str, dict]) -> Iterator[dict[str, Any]]:
        """生成网格参数组合"""
        keys = list(param_space.keys())
        value_lists: list[list[Any]] = []
        for k in keys:
            spec = param_space[k]
            t = spec.get("type", "int")
            if t == "categorical":
                value_lists.append(list(spec["choices"]))
            elif t == "int":
                low, high = int(spec["low"]), int(spec["high"])
                step = int(spec.get("step", 1))
                value_lists.append(list(range(low, high + 1, step)))
            elif t == "float":
                low, high = float(spec["low"]), float(spec["high"])
                step = float(spec.get("step", (high - low) / 10))
                n = int(round((high - low) / step)) + 1
                value_lists.append([low + i * step for i in range(n)])
            else:
                raise ValueError(f"未知参数类型: {t}")
        for combo in itertools.product(*value_lists):
            yield dict(zip(keys, combo))

    def _search_grid(
        self,
        strategy_type: str,
        version: str,
        param_space: dict[str, dict],
        base_config: dict,
    ) -> OptimizationReport:
        """网格搜索降级方案"""
        all_combos = list(self._grid(param_space))
        total = len(all_combos)
        if total > self.n_trials:
            logger.warning(
                f"网格规模 {total} > n_trials {self.n_trials}，随机采样 {self.n_trials} 组"
            )
            random.seed(42)
            all_combos = random.sample(all_combos, self.n_trials)

        report = OptimizationReport(
            strategy_type=strategy_type,
            version=version,
            metric=self.metric,
            backend="grid",
        )
        best_sign = -1.0 if self.direction == "maximize" else 1.0
        best_value = best_sign * 1e18

        for i, params in enumerate(all_combos):
            logger.info(f"网格试验 {i+1}/{len(all_combos)}: {params}")
            try:
                value, metrics = self._evaluate(strategy_type, version, params, base_config)
            except Exception as e:
                logger.warning(f"试验失败 {params}: {e}")
                continue

            trial = TrialResult(params=params, value=value, metrics=metrics)
            report.trials.append(trial)
            report.n_trials += 1

            better = (
                value > best_value
                if self.direction == "maximize"
                else value < best_value
            )
            if better:
                best_value = value
                report.best_value = value
                report.best_params = dict(params)
                report.best_metrics = metrics

        if report.n_trials == 0:
            logger.warning("所有试验均失败")
        return report

    def _search_optuna(
        self,
        strategy_type: str,
        version: str,
        param_space: dict[str, dict],
        base_config: dict,
    ) -> OptimizationReport:
        """Optuna 贝叶斯优化"""
        report = OptimizationReport(
            strategy_type=strategy_type,
            version=version,
            metric=self.metric,
            backend="optuna",
        )

        def objective(trial: "optuna.Trial") -> float:
            params: dict[str, Any] = {}
            for k, spec in param_space.items():
                t = spec.get("type", "int")
                if t == "categorical":
                    params[k] = trial.suggest_categorical(k, spec["choices"])
                elif t == "int":
                    params[k] = trial.suggest_int(
                        k, int(spec["low"]), int(spec["high"]),
                        step=int(spec.get("step", 1)),
                    )
                elif t == "float":
                    if spec.get("log"):
                        params[k] = trial.suggest_float(
                            k, float(spec["low"]), float(spec["high"]), log=True
                        )
                    else:
                        params[k] = trial.suggest_float(
                            k, float(spec["low"]), float(spec["high"])
                        )
                else:
                    raise ValueError(f"未知参数类型: {t}")
            try:
                value, metrics = self._evaluate(strategy_type, version, params, base_config)
            except Exception as e:
                logger.warning(f"试验失败 {params}: {e}")
                return 0.0
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            report.trials.append(TrialResult(params=params, value=value, metrics=metrics))
            report.n_trials += 1
            return value

        study = optuna.create_study(direction=self.direction)
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)

        best = study.best_trial
        report.best_value = best.value
        report.best_params = best.params
        report.best_metrics = best.user_attrs.get("metrics", {})

        return report

    def search(
        self,
        strategy_type: str,
        version: str,
        param_space: dict[str, dict],
    ) -> OptimizationReport:
        """执行参数搜索

        Args:
            strategy_type: 策略类型
            version: 版本号
            param_space: 参数空间（见模块 docstring）

        Returns:
            OptimizationReport
        """
        if not param_space:
            raise ValueError("param_space 不能为空")

        base_config = VersionManager.load_config(strategy_type, version)
        logger.info(
            f"开始参数搜索: {strategy_type} {version}, "
            f"backend={'optuna' if _HAS_OPTUNA else 'grid'}, "
            f"n_trials={self.n_trials}, metric={self.metric}"
        )

        if _HAS_OPTUNA:
            return self._search_optuna(strategy_type, version, param_space, base_config)
        return self._search_grid(strategy_type, version, param_space, base_config)


__all__ = [
    "ParamSearcher",
    "OptimizationReport",
    "TrialResult",
]
