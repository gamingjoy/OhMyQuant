"""跟踪模块

提供实验跟踪和训练日志功能：
  - 实验记录（参数、结果、指标）
  - 实验对比和搜索
  - 训练进度日志
  - 指标变化跟踪

用法：
    from ohmyquant.tracking import ExperimentTracker, TrainingLogger

    tracker = ExperimentTracker()
    exp_id = tracker.start_experiment("策略A_v1测试", "ycj", "v1")
    tracker.log_performance(exp_id, daily_returns)
    tracker.end_experiment(exp_id)

    logger = TrainingLogger()
    logger.log_epoch(epoch=1, train_loss=0.01, valid_loss=0.012)
"""
from .logger import TrainingHistory, TrainingLogger
from .tracker import Experiment, ExperimentTracker

__all__ = [
    # 实验跟踪
    "Experiment",
    "ExperimentTracker",
    # 训练日志
    "TrainingHistory",
    "TrainingLogger",
]
