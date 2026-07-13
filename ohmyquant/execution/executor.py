"""交易执行器

提供模拟执行器（回测用）和实盘执行器接口（预留券商对接）。

执行器不通过插件注册系统，因为执行模式（模拟 vs 实盘）是运行时决策，
非策略配置的一部分。通过 create_executor() 工厂方法创建。

用法:
    from ohmyquant.execution import create_executor
    executor = create_executor({"mode": "simulated"})
    trades = BaseExecutor.compute_trades(old_weights, new_weights)
    result = executor.execute_trades(trades, "2024-01-15", old_weights)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.logging import get_logger
from ..core.types import WeightMap

logger = get_logger(__name__)


@dataclass
class Trade:
    """单笔交易

    Attributes:
        code: 证券代码
        direction: 交易方向 "buy" / "sell"
        weight: 权重变化量（正数）
        price: 交易价格（可选，实盘用）
        date: 交易日期 "YYYY-MM-DD"
    """

    code: str
    direction: str  # "buy" / "sell"
    weight: float
    price: float = 0.0
    date: str = ""


@dataclass
class ExecutionResult:
    """执行结果

    Attributes:
        trades: 已执行的交易列表
        total_cost: 总交易成本
        success: 是否全部成功
        message: 附加信息
    """

    trades: list[Trade] = field(default_factory=list)
    total_cost: float = 0.0
    success: bool = True
    message: str = ""


class BaseExecutor(ABC):
    """交易执行器抽象基类"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def execute_trades(
        self,
        trades: list[Trade],
        date: str,
        current_weights: WeightMap,
    ) -> ExecutionResult:
        """执行交易

        Args:
            trades: 待执行的交易列表
            date: 交易日期
            current_weights: 当前持仓权重

        Returns:
            ExecutionResult
        """
        ...

    @staticmethod
    def compute_trades(
        old_weights: WeightMap, new_weights: WeightMap
    ) -> list[Trade]:
        """计算从旧权重到新权重需要的交易列表

        权重增加 → buy 交易
        权重减少 → sell 交易

        Args:
            old_weights: 旧持仓权重
            new_weights: 新持仓权重

        Returns:
            交易列表
        """
        trades: list[Trade] = []
        all_codes = set(old_weights) | set(new_weights)

        for code in all_codes:
            old_w = old_weights.get(code, 0.0)
            new_w = new_weights.get(code, 0.0)
            delta = new_w - old_w

            if delta > 1e-9:
                trades.append(Trade(code=code, direction="buy", weight=delta))
            elif delta < -1e-9:
                trades.append(Trade(code=code, direction="sell", weight=-delta))

        return trades


class SimulatedExecutor(BaseExecutor):
    """模拟执行器（回测用）

    记录交易到 trade_log，不实际执行。用于回测引擎中跟踪持仓变化。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.trade_log: list[Trade] = []

    def execute_trades(
        self,
        trades: list[Trade],
        date: str,
        current_weights: WeightMap,
    ) -> ExecutionResult:
        # 记录交易（设置日期）
        for trade in trades:
            trade.date = date
            self.trade_log.append(trade)
            logger.debug(
                f"模拟交易 {date}: {trade.direction} {trade.code} "
                f"权重={trade.weight:.4f}"
            )

        return ExecutionResult(
            trades=trades,
            success=True,
            message=f"模拟执行 {len(trades)} 笔交易",
        )


class LiveExecutor(BaseExecutor):
    """实盘执行器（预留接口）

    实际对接券商接口时实现此类。当前抛出 NotImplementedError。
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.broker = self.config.get("broker", "")
        self.api_key = self.config.get("api_key", "")

    def execute_trades(
        self,
        trades: list[Trade],
        date: str,
        current_weights: WeightMap,
    ) -> ExecutionResult:
        raise NotImplementedError(
            "实盘执行器尚未实现，请使用 SimulatedExecutor（mode='simulated'）"
        )


def create_executor(config: dict | None = None) -> BaseExecutor:
    """工厂方法：根据配置创建执行器

    Args:
        config: 执行器配置 dict，需包含 mode 字段。
                mode 可选: simulated / live
                未指定 mode 时默认 simulated

    Returns:
        BaseExecutor 实例
    """
    cfg = config or {}
    mode = cfg.get("mode", "simulated")

    if mode == "live":
        return LiveExecutor(cfg)
    return SimulatedExecutor(cfg)


__all__ = [
    "Trade",
    "ExecutionResult",
    "BaseExecutor",
    "SimulatedExecutor",
    "LiveExecutor",
    "create_executor",
]
