"""并行计算工具

提供线程池和进程池封装，用于加速因子计算和批量回测。
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable, TypeVar

from .logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def parallel_map(
    func: Callable[..., R],
    items: Iterable[T],
    mode: str = "thread",
    max_workers: int | None = None,
    chunksize: int = 1,
    **kwargs,
) -> list[R]:
    """并行 map

    Args:
        func: 处理函数
        items: 待处理数据
        mode: "thread"（IO 密集型）或 "process"（CPU 密集型）
        max_workers: 最大并发数，None 则自动
        chunksize: 每个任务的数据块大小（仅 process 模式）
        **kwargs: 传给 func 的额外参数
    """
    items_list = list(items)
    if not items_list:
        return []

    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, len(items_list))

    executor_cls = ThreadPoolExecutor if mode == "thread" else ProcessPoolExecutor

    results: list[R | None] = [None] * len(items_list)
    with executor_cls(max_workers=max_workers) as executor:
        future_to_idx = {}
        for idx, item in enumerate(items_list):
            future = executor.submit(func, item, **kwargs)
            future_to_idx[future] = idx

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error(f"并行任务失败 idx={idx}: {e}")
                results[idx] = None

    return [r for r in results if r is not None]


def run_backtests_parallel(
    backtest_fn: Callable,
    configs: Iterable[Any],
    max_workers: int | None = None,
) -> list:
    """并行运行多个回测

    Args:
        backtest_fn: 回测函数，接受一个 config 参数
        configs: 配置列表
        max_workers: 最大并发数
    """
    return parallel_map(backtest_fn, configs, mode="process", max_workers=max_workers)


__all__ = ["parallel_map", "run_backtests_parallel"]
