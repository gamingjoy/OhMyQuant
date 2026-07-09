"""实验跟踪

提供策略实验的跟踪和管理功能：
  - 实验记录（参数、结果、指标）
  - 实验对比
  - 实验存储（本地文件/数据库）
  - 实验搜索和筛选

参考：MLflow、Weights & Biases 的设计理念
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import polars as pl

from ..analysis.metrics import PerformanceMetrics, compute_metrics
from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Experiment:
    """实验记录"""

    id: str
    name: str
    strategy_type: str
    strategy_version: str
    params: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    performance_metrics: PerformanceMetrics | None = None
    start_time: str = ""
    end_time: str = ""
    status: str = "running"
    tags: Dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "strategy_type": self.strategy_type,
            "strategy_version": self.strategy_version,
            "params": self.params,
            "metrics": self.metrics,
            "performance_metrics": self.performance_metrics.__dict__ if self.performance_metrics else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "tags": self.tags,
            "notes": self.notes,
        }


class ExperimentTracker:
    """实验跟踪器"""

    def __init__(self, storage_path: str = "./experiments"):
        """初始化

        Args:
            storage_path: 实验数据存储路径
        """
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._experiments: Dict[str, Experiment] = {}
        self._load_experiments()

    def start_experiment(
        self,
        name: str,
        strategy_type: str,
        strategy_version: str,
        params: Dict[str, Any] | None = None,
        tags: Dict[str, str] | None = None,
    ) -> str:
        """开始新实验

        Args:
            name: 实验名称
            strategy_type: 策略类型
            strategy_version: 策略版本
            params: 参数字典
            tags: 标签字典

        Returns:
            str: 实验 ID
        """
        exp_id = f"exp_{int(time.time())}"
        experiment = Experiment(
            id=exp_id,
            name=name,
            strategy_type=strategy_type,
            strategy_version=strategy_version,
            params=params or {},
            tags=tags or {},
            start_time=datetime.now().isoformat(),
            status="running",
        )
        self._experiments[exp_id] = experiment
        logger.info(f"开始实验: {exp_id} - {name}")
        return exp_id

    def log_params(self, exp_id: str, params: Dict[str, Any]) -> None:
        """记录参数

        Args:
            exp_id: 实验 ID
            params: 参数字典
        """
        if exp_id not in self._experiments:
            logger.warning(f"实验不存在: {exp_id}")
            return
        self._experiments[exp_id].params.update(params)

    def log_metrics(self, exp_id: str, metrics: Dict[str, float]) -> None:
        """记录指标

        Args:
            exp_id: 实验 ID
            metrics: 指标字典
        """
        if exp_id not in self._experiments:
            logger.warning(f"实验不存在: {exp_id}")
            return
        self._experiments[exp_id].metrics.update(metrics)

    def log_performance(self, exp_id: str, returns: np.ndarray) -> None:
        """记录绩效指标

        Args:
            exp_id: 实验 ID
            returns: 每日收益序列
        """
        if exp_id not in self._experiments:
            logger.warning(f"实验不存在: {exp_id}")
            return
        performance_metrics = compute_metrics(returns)
        self._experiments[exp_id].performance_metrics = performance_metrics
        self._experiments[exp_id].metrics.update({
            "total_return": performance_metrics.total_return,
            "annualized_return": performance_metrics.annualized_return,
            "sharpe_ratio": performance_metrics.sharpe_ratio,
            "max_drawdown": performance_metrics.max_drawdown,
        })

    def end_experiment(self, exp_id: str, notes: str = "") -> None:
        """结束实验

        Args:
            exp_id: 实验 ID
            notes: 备注
        """
        if exp_id not in self._experiments:
            logger.warning(f"实验不存在: {exp_id}")
            return
        self._experiments[exp_id].end_time = datetime.now().isoformat()
        self._experiments[exp_id].status = "completed"
        self._experiments[exp_id].notes = notes
        self._save_experiment(self._experiments[exp_id])
        logger.info(f"实验完成: {exp_id}")

    def get_experiment(self, exp_id: str) -> Optional[Experiment]:
        """获取实验记录

        Args:
            exp_id: 实验 ID

        Returns:
            Experiment 或 None
        """
        return self._experiments.get(exp_id)

    def list_experiments(self) -> List[Experiment]:
        """列出所有实验

        Returns:
            List[Experiment]
        """
        return list(self._experiments.values())

    def search_experiments(
        self,
        strategy_type: str | None = None,
        strategy_version: str | None = None,
        status: str | None = None,
        tags: Dict[str, str] | None = None,
    ) -> List[Experiment]:
        """搜索实验

        Args:
            strategy_type: 策略类型
            strategy_version: 策略版本
            status: 状态
            tags: 标签筛选

        Returns:
            List[Experiment]
        """
        results = []
        for exp in self._experiments.values():
            if strategy_type and exp.strategy_type != strategy_type:
                continue
            if strategy_version and exp.strategy_version != strategy_version:
                continue
            if status and exp.status != status:
                continue
            if tags:
                match = True
                for key, value in tags.items():
                    if exp.tags.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            results.append(exp)
        return results

    def compare_experiments(self, exp_ids: List[str]) -> pl.DataFrame:
        """对比多个实验

        Args:
            exp_ids: 实验 ID 列表

        Returns:
            polars DataFrame
        """
        rows = []
        for exp_id in exp_ids:
            exp = self._experiments.get(exp_id)
            if exp and exp.performance_metrics:
                pm = exp.performance_metrics
                rows.append({
                    "exp_id": exp.id,
                    "name": exp.name,
                    "strategy": f"{exp.strategy_type}_{exp.strategy_version}",
                    "total_return": pm.total_return,
                    "annualized_return": pm.annualized_return,
                    "annualized_volatility": pm.annualized_volatility,
                    "sharpe_ratio": pm.sharpe_ratio,
                    "sortino_ratio": pm.sortino_ratio,
                    "max_drawdown": pm.max_drawdown,
                    "calmar_ratio": pm.calmar_ratio,
                    "status": exp.status,
                })
        return pl.DataFrame(rows).sort("sharpe_ratio", descending=True)

    def _save_experiment(self, experiment: Experiment) -> None:
        """保存实验到文件

        Args:
            experiment: 实验对象
        """
        filepath = os.path.join(self.storage_path, f"{experiment.id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(experiment.to_dict(), f, indent=2, ensure_ascii=False)

    def _load_experiments(self) -> None:
        """加载所有已保存的实验"""
        for filename in os.listdir(self.storage_path):
            if filename.endswith(".json"):
                filepath = os.path.join(self.storage_path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        exp = Experiment(
                            id=data["id"],
                            name=data["name"],
                            strategy_type=data["strategy_type"],
                            strategy_version=data["strategy_version"],
                            params=data.get("params", {}),
                            metrics=data.get("metrics", {}),
                            start_time=data.get("start_time", ""),
                            end_time=data.get("end_time", ""),
                            status=data.get("status", "completed"),
                            tags=data.get("tags", {}),
                            notes=data.get("notes", ""),
                        )
                        if data.get("performance_metrics"):
                            pm_data = data["performance_metrics"]
                            exp.performance_metrics = PerformanceMetrics(**pm_data)
                        self._experiments[exp.id] = exp
                except Exception as e:
                    logger.error(f"加载实验失败: {filename}, 错误: {e}")

    def delete_experiment(self, exp_id: str) -> None:
        """删除实验

        Args:
            exp_id: 实验 ID
        """
        if exp_id not in self._experiments:
            logger.warning(f"实验不存在: {exp_id}")
            return
        filepath = os.path.join(self.storage_path, f"{exp_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
        del self._experiments[exp_id]
        logger.info(f"实验已删除: {exp_id}")


__all__ = ["Experiment", "ExperimentTracker"]
