"""训练日志

提供策略训练过程的日志记录功能：
  - 训练进度日志
  - 指标变化跟踪
  - 训练结果汇总
  - 日志文件管理

功能：
  - TrainingLogger: 训练日志记录器
  - TrainingHistory: 训练历史记录
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

import numpy as np

from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TrainingHistory:
    """训练历史记录"""

    epoch: int = 0
    train_loss: float = 0.0
    valid_loss: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "epoch": self.epoch,
            "train_loss": self.train_loss,
            "valid_loss": self.valid_loss,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
        }


class TrainingLogger:
    """训练日志记录器"""

    def __init__(self, log_dir: str = "./logs", run_name: str | None = None):
        """初始化

        Args:
            log_dir: 日志目录
            run_name: 运行名称（自动生成）
        """
        self.log_dir = log_dir
        self.run_name = run_name or f"run_{int(time.time())}"
        self.run_dir = os.path.join(log_dir, self.run_name)
        os.makedirs(self.run_dir, exist_ok=True)

        self.history: List[TrainingHistory] = []
        self.start_time = datetime.now()
        self._log_file = os.path.join(self.run_dir, "training.log")
        self._history_file = os.path.join(self.run_dir, "history.json")

        with open(self._log_file, "w", encoding="utf-8") as f:
            f.write(f"训练开始: {self.start_time.isoformat()}\n")
            f.write(f"运行名称: {self.run_name}\n")
            f.write("=" * 60 + "\n")

        logger.info(f"训练日志已创建: {self.run_dir}")

    def log_epoch(
        self,
        epoch: int,
        train_loss: float,
        valid_loss: float | None = None,
        metrics: Dict[str, float] | None = None,
    ) -> None:
        """记录轮次训练结果

        Args:
            epoch: 轮次
            train_loss: 训练损失
            valid_loss: 验证损失（可选）
            metrics: 指标字典（可选）
        """
        history = TrainingHistory(
            epoch=epoch,
            train_loss=train_loss,
            valid_loss=valid_loss or 0.0,
            metrics=metrics or {},
            timestamp=datetime.now().isoformat(),
        )
        self.history.append(history)

        log_line = (
            f"[Epoch {epoch}] "
            f"train_loss={train_loss:.6f} "
            f"valid_loss={valid_loss:.6f}" if valid_loss else ""
        )
        if metrics:
            for key, value in metrics.items():
                log_line += f" {key}={value:.4f}"

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

        self._save_history()

        logger.info(log_line)

    def log_message(self, message: str, level: str = "INFO") -> None:
        """记录自定义消息

        Args:
            message: 消息内容
            level: 日志级别（INFO/WARN/ERROR）
        """
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] [{level}] {message}"

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

        if level == "ERROR":
            logger.error(message)
        elif level == "WARN":
            logger.warning(message)
        else:
            logger.info(message)

    def log_params(self, params: Dict[str, Any]) -> None:
        """记录超参数

        Args:
            params: 参数字典
        """
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write("\n超参数:\n")
            for key, value in params.items():
                f.write(f"  {key}: {value}\n")

        logger.info(f"超参数已记录: {list(params.keys())}")

    def log_results(self, results: Dict[str, Any]) -> None:
        """记录最终结果

        Args:
            results: 结果字典
        """
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"训练结束: {end_time.isoformat()}\n")
            f.write(f"训练时长: {duration:.2f} 秒\n")
            f.write("最终结果:\n")
            for key, value in results.items():
                f.write(f"  {key}: {value}\n")

        logger.info(f"训练完成，时长: {duration:.2f} 秒")

    def get_best_epoch(self, metric: str = "valid_loss", maximize: bool = False) -> TrainingHistory | None:
        """获取最佳轮次

        Args:
            metric: 指标名称
            maximize: 是否最大化（默认最小化）

        Returns:
            TrainingHistory 或 None
        """
        if not self.history:
            return None

        best = self.history[0]
        for h in self.history:
            if metric == "valid_loss":
                value = h.valid_loss
            elif metric == "train_loss":
                value = h.train_loss
            else:
                value = h.metrics.get(metric, float("-inf"))

            if maximize:
                if value > (best.metrics.get(metric, float("-inf")) if metric != "valid_loss" and metric != "train_loss" else getattr(best, metric, float("-inf"))):
                    best = h
            else:
                if value < (best.metrics.get(metric, float("inf")) if metric != "valid_loss" and metric != "train_loss" else getattr(best, metric, float("inf"))):
                    best = h

        return best

    def _save_history(self) -> None:
        """保存训练历史"""
        with open(self._history_file, "w", encoding="utf-8") as f:
            json.dump([h.to_dict() for h in self.history], f, indent=2)

    def load_history(self, run_name: str) -> List[TrainingHistory]:
        """加载训练历史

        Args:
            run_name: 运行名称

        Returns:
            List[TrainingHistory]
        """
        history_file = os.path.join(self.log_dir, run_name, "history.json")
        if not os.path.exists(history_file):
            logger.warning(f"历史文件不存在: {history_file}")
            return []

        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return [TrainingHistory(**h) for h in data]

    def list_runs(self) -> List[str]:
        """列出所有运行

        Returns:
            List[str]: 运行名称列表
        """
        if not os.path.exists(self.log_dir):
            return []
        return [
            d for d in os.listdir(self.log_dir)
            if os.path.isdir(os.path.join(self.log_dir, d))
        ]


__all__ = ["TrainingHistory", "TrainingLogger"]
