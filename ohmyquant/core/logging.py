"""日志系统（基于 loguru）

提供统一的日志配置和便捷接口。
默认输出到控制台和文件，支持通过配置文件自定义。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONFIGURED = False

_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging(
    level: str = "INFO",
    log_dir: str | Path | None = None,
    rotation: str = "10 MB",
    retention: str = "30 days",
    fmt: str = _DEFAULT_FORMAT,
    colorize: bool = True,
) -> None:
    """配置日志系统

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_dir: 日志目录，None 则只输出到控制台
        rotation: 日志轮转大小
        retention: 日志保留时长
        fmt: 日志格式
        colorize: 控制台彩色输出
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        level=level,
        format=fmt,
        colorize=colorize,
        backtrace=True,
        diagnose=False,
    )

    # 文件输出
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_dir / "ohmyquant_{time:YYYY-MM-DD}.log"),
            level=level,
            format=fmt,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
            backtrace=True,
            diagnose=False,
        )

    _CONFIGURED = True


def get_logger(name: str | None = None):
    """获取 logger

    Args:
        name: 模块名，None 则返回全局 logger
    """
    if name:
        return logger.bind(name=name)
    return logger


# 默认初始化（控制台 INFO）
setup_logging()

__all__ = ["setup_logging", "get_logger", "logger"]
