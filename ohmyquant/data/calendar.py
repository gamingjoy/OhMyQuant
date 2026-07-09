"""交易日历

提供交易日历查询功能，基于数据源的交易日历或内置规则。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import DataSource

from ..core.logging import get_logger

logger = get_logger(__name__)


class TradeCalendar:
    """交易日历

    从数据源加载交易日历，或使用内置规则（周一到周五，排除节假日需数据源提供）。
    """

    def __init__(self, source: "DataSource | None" = None):
        self._source = source
        self._calendar_cache: list[str] | None = None

    def _ensure_calendar(self, start_date: str, end_date: str) -> list[str]:
        """确保日历已加载"""
        if self._source is not None:
            return self._source.get_trade_calendar(start_date, end_date)
        # 无数据源时，用内置规则（仅排除周末，节假日需数据源）
        return self._builtin_calendar(start_date, end_date)

    @staticmethod
    def _builtin_calendar(start_date: str, end_date: str) -> list[str]:
        """内置日历（仅排除周末，不处理节假日）"""
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        days: list[str] = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # 周一到周五
                days.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return days

    def get_trade_days(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[str]:
        """获取交易日列表

        Args:
            start_date: 开始日期，None 则从 2010-01-01
            end_date: 结束日期，None 则到今天
        """
        start_date = start_date or "2010-01-01"
        end_date = end_date or date.today().strftime("%Y-%m-%d")
        return self._ensure_calendar(start_date, end_date)

    def get_next_trade_day(self, current_date: str, n: int = 1) -> str:
        """获取当前日期后第 n 个交易日"""
        days = self.get_trade_days(current_date, (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=n * 30)).strftime("%Y-%m-%d"))
        idx = days.index(current_date) if current_date in days else 0
        for d in days:
            if d > current_date:
                idx = days.index(d)
                break
        target_idx = min(idx + n, len(days) - 1)
        return days[target_idx]

    def get_prev_trade_day(self, current_date: str, n: int = 1) -> str:
        """获取当前日期前第 n 个交易日"""
        end = datetime.strptime(current_date, "%Y-%m-%d")
        start = end - timedelta(days=n * 30)
        days = self.get_trade_days(start.strftime("%Y-%m-%d"), current_date)
        # 找到 current_date 或之前的最近交易日
        valid = [d for d in days if d <= current_date]
        if not valid:
            return current_date
        idx = valid.index(current_date) if current_date in valid else len(valid) - 1
        target_idx = max(idx - n, 0)
        return valid[target_idx]

    def is_trade_day(self, check_date: str) -> bool:
        """判断是否为交易日"""
        days = self._ensure_calendar(check_date, check_date)
        return check_date in days

    def count_trade_days(self, start_date: str, end_date: str) -> int:
        """统计区间内交易日数量"""
        return len(self.get_trade_days(start_date, end_date))


__all__ = ["TradeCalendar"]
