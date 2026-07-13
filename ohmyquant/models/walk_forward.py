"""Walk-Forward 滚动训练

模型级 walk-forward：将时间序列分割为多个训练/测试窗口，
每个窗口用训练数据拟合模型，在测试窗口上预测。
"""
from __future__ import annotations

from typing import Any, Iterator

from ..core.logging import get_logger

logger = get_logger(__name__)


class WalkForwardRunner:
    """滚动训练分割生成器

    Usage:
        runner = WalkForwardRunner(train_window=252, test_window=63, step=63)
        for train_dates, test_dates in runner.splits(all_dates):
            pipeline.train(data, train_dates)
            predictions = pipeline.predict(data, test_dates)
    """

    def __init__(
        self,
        train_window: int = 252,
        test_window: int = 63,
        step: int = 63,
        retrain_freq: int = 21,
        min_train_size: int = 100,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.retrain_freq = retrain_freq
        self.min_train_size = min_train_size

    def splits(self, dates: list[str]) -> Iterator[tuple[list[str], list[str]]]:
        """生成训练/测试窗口分割

        Args:
            dates: 完整日期列表（已排序）

        Yields:
            (train_dates, test_dates) 元组
        """
        n = len(dates)
        if n < self.train_window + self.test_window:
            logger.warning(
                f"日期数 {n} 不足以分割（需 >={self.train_window + self.test_window}）"
            )
            return

        start = 0
        while start + self.train_window + self.test_window <= n:
            train_end = start + self.train_window
            test_end = min(train_end + self.test_window, n)
            train_dates = dates[start:train_end]
            test_dates = dates[train_end:test_end]
            yield train_dates, test_dates
            start += self.step

    def run(
        self,
        pipeline: Any,
        data: Any,
        dates: list[str],
        predict_fn: Any | None = None,
    ) -> dict[str, Any]:
        """运行 walk-forward 训练和预测

        Args:
            pipeline: TrainingPipeline 实例
            data: 数据对象（由 predict_fn 解释）
            dates: 完整日期列表
            predict_fn: 自定义预测函数 (pipeline, data, train_dates, test_dates) -> dict

        Returns:
            {window_idx: predictions}
        """
        results: dict[int, Any] = {}
        for window_idx, (train_dates, test_dates) in enumerate(self.splits(dates)):
            logger.info(
                f"Walk-forward 窗口 {window_idx}: "
                f"train {train_dates[0]}~{train_dates[-1]} ({len(train_dates)}天), "
                f"test {test_dates[0]}~{test_dates[-1]} ({len(test_dates)}天)"
            )

            if predict_fn is not None:
                pred = predict_fn(pipeline, data, train_dates, test_dates)
            else:
                pred = {"train_dates": train_dates, "test_dates": test_dates}

            results[window_idx] = pred

        return results


__all__ = ["WalkForwardRunner"]
