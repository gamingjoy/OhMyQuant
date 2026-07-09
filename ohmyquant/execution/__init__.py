"""执行/调仓系统

提供调仓决策、成本模型、调度器和执行器：
  - CostModel: 交易成本模型（股票 stock_cn / ETF etf_cn）
  - Rebalancer: 调仓决策器（cost_benefit / simple / none）
  - Scheduler: 调仓调度器（calendar / adaptive）
  - Executor: 交易执行器（simulated / live）

用法:
    from ohmyquant.execution import create_rebalancer, create_cost_model

    # 成本模型
    cm = create_cost_model({"name": "stock_cn"})
    cost = cm.estimate(old_weights, new_weights)

    # 调仓器
    rb = create_rebalancer({"method": "cost_benefit", "cost_model": {"name": "stock_cn"}})
    result = rb.decide(current_weights, target_weights, scores=scores)

    # 调度器
    sched = create_scheduler({"frequency": "monthly"})
    rebal_dates = sched.get_rebalance_dates(dates)
"""
from .base import BaseRebalancer, RebalanceResult
from .cost_model import (
    BaseCostModel,
    ETFCostModel,
    StockCostModel,
    create_cost_model,
)
from .executor import (
    BaseExecutor,
    ExecutionResult,
    LiveExecutor,
    SimulatedExecutor,
    Trade,
    create_executor,
)
from .rebalancer import (
    CostBenefitRebalancer,
    NoOpRebalancer,
    SimpleRebalancer,
    create_rebalancer,
)
from .scheduler import (
    AdaptiveScheduler,
    BaseScheduler,
    CalendarScheduler,
    create_scheduler,
)

__all__ = [
    # 基类与数据类
    "RebalanceResult",
    "BaseRebalancer",
    "BaseCostModel",
    "BaseScheduler",
    "BaseExecutor",
    "Trade",
    "ExecutionResult",
    # 成本模型
    "StockCostModel",
    "ETFCostModel",
    "MixedCostModel",
    "create_cost_model",
    # 调仓器
    "CostBenefitRebalancer",
    "SimpleRebalancer",
    "NoOpRebalancer",
    "create_rebalancer",
    # 调度器
    "CalendarScheduler",
    "AdaptiveScheduler",
    "create_scheduler",
    # 执行器
    "SimulatedExecutor",
    "LiveExecutor",
    "create_executor",
]
