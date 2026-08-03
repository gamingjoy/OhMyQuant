"""调度器单元测试

覆盖两个调度器插件：
  - CalendarScheduler（日历频率：daily/weekly/monthly/quarterly）
  - AdaptiveScheduler（自适应：日历 + 波动率触发）
  - create_scheduler 工厂方法
"""
import polars as pl
import pytest

from ohmyquant.execution.scheduler import (
    AdaptiveScheduler,
    CalendarScheduler,
    create_scheduler,
)


def _weekdays(start: str, n: int) -> list[str]:
    """生成 n 个连续工作日（跳过周末）"""
    from datetime import datetime, timedelta

    dt = datetime.strptime(start, "%Y-%m-%d")
    dates = []
    while len(dates) < n:
        if dt.weekday() < 5:  # 0=Mon ... 4=Fri
            dates.append(dt.strftime("%Y-%m-%d"))
        dt += timedelta(days=1)
    return dates


class TestCalendarScheduler:
    """日历调度器测试"""

    def test_weekly_monday(self):
        """周频周一调仓：每周第一个周一"""
        dates = _weekdays("2024-03-04", 20)  # 4 weeks starting Monday
        scheduler = CalendarScheduler({"frequency": "weekly", "weekday": 0})
        result = scheduler.get_rebalance_dates(dates)

        # 周一: Mar 4, 11, 18, 25
        assert "2024-03-04" in result
        assert "2024-03-11" in result
        assert "2024-03-18" in result
        assert "2024-03-25" in result
        assert len(result) == 4

    def test_weekly_fallback(self):
        """周频目标日为假期时用本周首个交易日兜底"""
        # Mar 1 is Friday, Mar 4 is Monday — 若 Mar 4 不在日期列表中
        dates = ["2024-03-01", "2024-03-05", "2024-03-06"]  # 跳过周一 Mar 4
        scheduler = CalendarScheduler({"frequency": "weekly", "weekday": 0})
        result = scheduler.get_rebalance_dates(dates)
        # Mar 1 作为本周兜底
        assert "2024-03-01" in result

    def test_monthly(self):
        """月频：每月首个交易日"""
        dates = [
            "2024-01-31",
            "2024-02-01", "2024-02-15", "2024-02-29",
            "2024-03-01", "2024-03-15",
            "2024-04-01",
        ]
        scheduler = CalendarScheduler({"frequency": "monthly"})
        result = scheduler.get_rebalance_dates(dates)

        assert "2024-01-31" in result
        assert "2024-02-01" in result
        assert "2024-03-01" in result
        assert "2024-04-01" in result
        assert len(result) == 4

    def test_quarterly(self):
        """季频：每季首个交易日"""
        dates = [
            "2024-01-15",  # Q1
            "2024-04-01",  # Q2
            "2024-07-01",  # Q3
            "2024-10-01",  # Q4
        ]
        scheduler = CalendarScheduler({"frequency": "quarterly"})
        result = scheduler.get_rebalance_dates(dates)

        assert result == set(dates)

    def test_daily(self):
        """日频：所有日期"""
        dates = _weekdays("2024-03-04", 5)
        scheduler = CalendarScheduler({"frequency": "daily"})
        result = scheduler.get_rebalance_dates(dates)
        assert result == set(dates)

    def test_empty_dates(self):
        """空日期列表返回空集"""
        scheduler = CalendarScheduler({"frequency": "monthly"})
        assert scheduler.get_rebalance_dates([]) == set()

    def test_default_frequency(self):
        """默认月频"""
        scheduler = CalendarScheduler({})
        assert scheduler.frequency == "monthly"

    def test_default_weekday(self):
        """默认 weekday=0（周一）"""
        scheduler = CalendarScheduler({})
        assert scheduler.weekday == 0


class TestAdaptiveScheduler:
    """自适应调度器测试"""

    def test_degrades_without_daily_returns(self):
        """无 daily_returns 时退化为日历逻辑"""
        dates = _weekdays("2024-03-04", 20)
        scheduler = AdaptiveScheduler({"frequency": "monthly"})
        result = scheduler.get_rebalance_dates(dates)

        # 应等于 CalendarScheduler 的结果
        cal = CalendarScheduler({"frequency": "monthly"})
        assert result == cal.get_rebalance_dates(dates)

    def test_low_volatility_no_trigger(self):
        """低波动率不触发额外调仓"""
        dates = _weekdays("2024-03-04", 40)  # 跨 Mar-Apr
        # 零收益 → 波动率为 0
        daily_returns = pl.Series("ret", [0.0] * 40)
        scheduler = AdaptiveScheduler({
            "frequency": "monthly",
            "vol_threshold": 0.3,
            "lookback": 15,
            "min_rebalance_interval": 5,
        })
        result = scheduler.get_rebalance_dates(dates, daily_returns=daily_returns)

        # 应等于月频基础调仓日
        cal = CalendarScheduler({"frequency": "monthly"})
        assert result == cal.get_rebalance_dates(dates)

    def test_high_volatility_triggers_extra_dates(self):
        """高波动率触发额外调仓日"""
        dates = _weekdays("2024-03-04", 40)  # 40 个工作日，跨 Mar-Apr
        # 交替 ±5% 收益 → 年化波动率 ≈ 0.05 * sqrt(242) ≈ 0.78 > 0.3
        daily_returns = pl.Series("ret", [0.05, -0.05] * 20)
        scheduler = AdaptiveScheduler({
            "frequency": "monthly",
            "vol_threshold": 0.3,
            "lookback": 15,
            "min_rebalance_interval": 5,
        })
        result = scheduler.get_rebalance_dates(dates, daily_returns=daily_returns)

        # 基础月频调仓日
        cal = CalendarScheduler({"frequency": "monthly"})
        base_dates = cal.get_rebalance_dates(dates)

        # 结果应严格大于基础日（有额外触发）
        assert len(result) > len(base_dates)
        # 基础日都应在结果中
        assert base_dates.issubset(result)
        # 触发日应在 lookback 之后
        # i=15 是第一个可触发的索引（lookback=15, window len=15>=10）
        assert dates[15] in result  # Mar 25

    def test_min_rebalance_interval_respected(self):
        """min_rebalance_interval 限制触发频率"""
        dates = _weekdays("2024-03-04", 40)
        daily_returns = pl.Series("ret", [0.05, -0.05] * 20)

        # 间隔=5：触发日为 i=15,20,25,30,35
        scheduler5 = AdaptiveScheduler({
            "frequency": "daily",  # daily base 不会和触发日重叠影响判断
            "vol_threshold": 0.3,
            "lookback": 15,
            "min_rebalance_interval": 5,
        })
        # 用 monthly 避免daily base干扰
        scheduler5 = AdaptiveScheduler({
            "frequency": "monthly",
            "vol_threshold": 0.3,
            "lookback": 15,
            "min_rebalance_interval": 5,
        })
        result5 = scheduler5.get_rebalance_dates(dates, daily_returns=daily_returns)

        # 间隔=10：触发日为 i=15,25,35
        scheduler10 = AdaptiveScheduler({
            "frequency": "monthly",
            "vol_threshold": 0.3,
            "lookback": 15,
            "min_rebalance_interval": 10,
        })
        result10 = scheduler10.get_rebalance_dates(dates, daily_returns=daily_returns)

        # 间隔越大，触发日越少
        assert len(result10) < len(result5)

    def test_empty_daily_returns_series(self):
        """空 daily_returns Series 退化为日历"""
        dates = _weekdays("2024-03-04", 20)
        scheduler = AdaptiveScheduler({"frequency": "monthly"})
        result = scheduler.get_rebalance_dates(dates, daily_returns=pl.Series("ret", []))
        cal = CalendarScheduler({"frequency": "monthly"})
        assert result == cal.get_rebalance_dates(dates)


class TestCreateScheduler:
    """工厂方法测试"""

    def test_create_calendar(self):
        s = create_scheduler({"frequency": "monthly"})
        assert isinstance(s, CalendarScheduler)

    def test_create_adaptive(self):
        s = create_scheduler({"frequency": "adaptive"})
        assert isinstance(s, AdaptiveScheduler)

    def test_create_default(self):
        """默认创建 CalendarScheduler（非 adaptive）"""
        s = create_scheduler({})
        assert isinstance(s, CalendarScheduler)

    def test_create_empty_config(self):
        s = create_scheduler(None)
        assert isinstance(s, CalendarScheduler)
