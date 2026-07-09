# OhMyQuant Phase 5: 调仓执行系统实施计划

## Context

Phase 4（回测引擎）已完成并通过端到端验证。当前回测引擎使用简单的 flat `transaction_cost`（`BacktestConfig.transaction_cost = 0.001`）计算交易成本，调仓日通过 `BaseAllocator.get_rebalance_dates()` 静态方法确定。

Phase 5 需要构建独立的 `ohmyquant/execution/` 模块，提供：
1. **精确成本模型**：支持股票（佣金+印花税+过户费）和 ETF（申购费+赎回费+7天惩罚）两类市场的真实成本计算
2. **成本收益权衡调仓器**：参考 ETF_portfolio 的成本收益模型，仅当净收益为正时执行调仓，跳过成本过高的调仓
3. **可插拔调度器**：日/周/月/季日历频率 + 自适应频率（波动率触发）
4. **执行器接口**：模拟执行器（回测）+ 实盘执行器接口（预留券商对接）

设计原则：插件化（复用已有 `PluginType.REBALANCER/COST_MODEL/SCHEDULER` 注册系统）、polars-first、配置驱动、向后兼容（`method: "none"` 保持 Phase 4 行为）。

## Current State

### 已存在的基础设施（无需重建）
- [core/plugin_system.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/plugin_system.py) — `PluginType.REBALANCER/COST_MODEL/SCHEDULER` 枚举 + `@register_rebalancer/@register_cost_model/@register_scheduler` 装饰器已定义
- [core/config_models.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/config_models.py#L125-L134) — `RebalanceConfig` 已存在（frequency/weekday/min_hold_days/cost_benefit_threshold/method）
- [engine/allocator.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/allocator.py#L88-L151) — `BaseAllocator.get_rebalance_dates()` 静态方法已实现日/周/月/季频率
- [engine/backtest.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py#L626-L633) — 现有 flat transaction cost 计算（集成点）

### 参考实现
- [ETF_portfolio/strategy/execution/cost_model.py](file:///D:/Work/Project/ETF_portfolio/strategy/execution/cost_model.py) — ETF 成本模型（C 类份额 7 天惩罚）
- [ETF_portfolio/strategy/execution/rebalancer.py](file:///D:/Work/Project/ETF_portfolio/strategy/execution/rebalancer.py) — 成本收益权衡调仓逻辑

## Proposed Changes

### 文件 1: `ohmyquant/execution/cost_model.py`（新建）

**What**: 成本模型 ABC + 股票/ETF 两类实现 + 工厂方法

**关键类签名**:
```python
class BaseCostModel(ABC):
    def __init__(self, config: dict | None = None): ...
    @abstractmethod
    def estimate(self, old_weights: WeightMap, new_weights: WeightMap,
                 hold_days_map: dict[str, int] | None = None) -> float: ...
    @abstractmethod
    def buy_cost(self, weight: float) -> float: ...
    @abstractmethod
    def sell_cost(self, weight: float, hold_days: int = 0) -> float: ...

@register_cost_model("stock_cn")
class StockCostModel(BaseCostModel):
    # commission_rate=0.00025, stamp_duty=0.0005, transfer_fee=0.00001
    # buy_cost = weight * (commission_rate + transfer_fee)
    # sell_cost = weight * (commission_rate + stamp_duty + transfer_fee)

@register_cost_model("etf_cn")
class ETFCostModel(BaseCostModel):
    # purchase_fee=0.0, redeem_fee_within_7d=0.015, redeem_fee_after_7d=0.0, min_hold_days=7
    # sell_cost = weight * (redeem_fee_within_7d if hold_days < min_hold_days else redeem_fee_after_7d)

def create_cost_model(config: dict | None = None) -> BaseCostModel:
    # PluginRegistry.create(PluginType.COST_MODEL, name, config)
```

**estimate() 算法**: 遍历 `set(old_weights) | set(new_weights)`，对每个 code 计算权重差 `delta = new - old`，`delta > 0` 用 `buy_cost(delta)`，`delta < 0` 用 `sell_cost(-delta, hold_days)`。

### 文件 2: `ohmyquant/execution/base.py`（新建）

**What**: `RebalanceResult` dataclass + `BaseRebalancer` ABC

```python
@dataclass
class RebalanceResult:
    need_rebalance: bool = False
    sells: list[str] = field(default_factory=list)
    buys: list[str] = field(default_factory=list)
    skipped_sells: list[dict] = field(default_factory=list)
    total_cost: float = 0.0
    total_benefit: float = 0.0
    final_weights: WeightMap = field(default_factory=dict)  # 实际执行后的权重（含跳过的卖出）

    @property
    def net_benefit(self) -> float:
        return self.total_benefit - self.total_cost

class BaseRebalancer(ABC):
    def __init__(self, config: dict | None = None):
        self.cost_benefit_threshold: float = cfg.get("cost_benefit_threshold", 0.0)
        self.min_hold_days: int = cfg.get("min_hold_days", 0)
    @abstractmethod
    def decide(self, current_weights: WeightMap, target_weights: WeightMap,
               hold_days_map: dict[str, int] | None = None,
               scores: dict[str, float] | None = None) -> RebalanceResult: ...
```

### 文件 3: `ohmyquant/execution/rebalancer.py`（新建）

**What**: 三个调仓器实现 + 工厂

- `@register_rebalancer("cost_benefit") CostBenefitRebalancer` — 核心实现，评估每个卖出候选的 `net_benefit = benefit - cost`，仅 `net_benefit > threshold` 时执行。`hold_days < min_hold_days` 强制跳过。跳过的卖出标的保留在 `final_weights` 中（从 `current_weights` 恢复），最后归一化。
- `@register_rebalancer("simple") SimpleRebalancer` — 直接采用目标权重，仅计算成本不权衡
- `@register_rebalancer("none") NoOpRebalancer` — 不调仓，`final_weights = current_weights`

`CostBenefitRebalancer.decide()` 核心逻辑（参考 ETF_portfolio `_evaluate_sells` + `_apply_decision`）:
1. 首次建仓（`current_weights` 为空）→ 直接买入全部目标
2. `sell_candidates = old_codes - new_codes`, `buy_candidates = new_codes - old_codes`
3. 对每个 sell_code：`cost = cost_model.sell_cost(1.0, hold_days)`, `benefit = max(best_buy_score - old_score, 0) * 0.1`, `net_benefit = benefit - cost`
4. 按 `net_benefit` 降序排列，`> threshold` 的执行卖出，配对最佳买入
5. 跳过的卖出标的保留在 `final_weights`（从 `current_weights` 恢复权重），归一化

### 文件 4: `ohmyquant/execution/scheduler.py`（新建）

**What**: 调度器 ABC + 日历/自适应实现 + 工厂

- `@register_scheduler("calendar") CalendarScheduler` — thin wrapper，委托给 `BaseAllocator.get_rebalance_dates(dates, self.frequency, self.weekday)`
- `@register_scheduler("adaptive") AdaptiveScheduler` — 日历频率 + 波动率触发。`get_rebalance_dates(dates, daily_returns=None)`：当 `daily_returns` 为 None 时退化为日历逻辑；否则检查近期年化波动率是否超阈值，超阈值且距上次调仓 >= `min_rebalance_interval` 天则追加调仓日

```python
class BaseScheduler(ABC):
    def __init__(self, config: dict | None = None):
        self.frequency: str = cfg.get("frequency", "monthly")
        self.weekday: int = cfg.get("weekday", 0)
    @abstractmethod
    def get_rebalance_dates(self, dates: list[str], **kwargs) -> set[str]: ...

def create_scheduler(config: dict | None = None) -> BaseScheduler:
    # frequency == "adaptive" → AdaptiveScheduler, 否则 → CalendarScheduler
```

### 文件 5: `ohmyquant/execution/executor.py`（新建）

**What**: 交易数据类 + 执行器 ABC + 模拟/实盘实现 + 工厂

```python
@dataclass
class Trade:
    code: str; direction: str; weight: float; price: float = 0.0; date: str = ""

@dataclass
class ExecutionResult:
    trades: list[Trade] = field(default_factory=list)
    total_cost: float = 0.0; success: bool = True; message: str = ""

class BaseExecutor(ABC):
    @abstractmethod
    def execute_trades(self, trades: list[Trade], date: str,
                       current_weights: WeightMap) -> ExecutionResult: ...
    @staticmethod
    def compute_trades(old_weights: WeightMap, new_weights: WeightMap) -> list[Trade]: ...

class SimulatedExecutor(BaseExecutor):
    # 记录到 self.trade_log，返回 ExecutionResult(success=True)

class LiveExecutor(BaseExecutor):
    # raise NotImplementedError("实盘执行器尚未实现")

def create_executor(config: dict | None = None) -> BaseExecutor:
    # mode == "live" → LiveExecutor, 否则 → SimulatedExecutor
```

**注**: 执行器不通过插件注册系统（`mode` 是运行时决策，非策略配置）。Phase 5 中 `SimulatedExecutor` 预留接口，暂不深度集成到回测主循环。

### 文件 6: `ohmyquant/execution/__init__.py`（新建）

模块导出，遵循 [engine/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/__init__.py) 模式。导出所有 Base ABC、具体实现、工厂方法。

### 文件 7: `ohmyquant/core/config_models.py`（修改）

在 `RebalanceConfig`（第 125-134 行）添加 `cost_model` 子配置字段：

```python
class RebalanceConfig(BaseModel):
    frequency: str = "monthly"
    weekday: int = Field(0, ge=0, le=6)
    min_hold_days: int = 0
    cost_benefit_threshold: float = 0.0
    method: str = "cost_benefit"
    cost_model: dict[str, Any] = Field(default_factory=lambda: {"name": "stock_cn"})  # 新增

    model_config = {"extra": "allow"}
```

`to_flat_dict()` 已包含 `"rebalance": self.rebalance.model_dump()`，无需修改。`from typing import Any` 已在第 8 行导入。

### 文件 8: `ohmyquant/engine/backtest.py`（修改 3 处）

**修改 1 — `__init__`（第 107-108 行后）**: 创建调度器和调仓器
```python
self.rebalance_freq = rebalance_cfg.get("frequency", "monthly")
self.rebalance_weekday = rebalance_cfg.get("weekday", 0)
self.rebalance_method = rebalance_cfg.get("method", "cost_benefit")

# 延迟导入避免循环依赖
from ..execution import create_scheduler, create_rebalancer
self.scheduler = create_scheduler(rebalance_cfg)
self.rebalancer = create_rebalancer(rebalance_cfg) if self.rebalance_method != "none" else None
```

**修改 2 — `_run_selection`（第 362 行）和 `_run_backtest_loop`（第 513 行）**: 替换调仓日计算
```python
# 旧: rebalance_dates = self.allocator.get_rebalance_dates(all_dates, self.rebalance_freq, self.rebalance_weekday)
# 新: rebalance_dates = self.scheduler.get_rebalance_dates(all_dates)
```

**修改 3 — `_run_backtest_loop` 交易成本（第 625-633 行）**: 双路径，向后兼容
```python
# 初始化区域添加: prev_effective_weights: dict[str, float] = {}

# 交易成本计算替换为:
if date_str in rebalance_dates and i >= bt_start_idx:
    if self.rebalancer is not None:
        new_eff_weights = self._compute_effective_weights(
            current_pool_stock_weights, pool_weights, effective_scale, self.max_stock_weight,
        )
        cost = self.rebalancer.cost_model.estimate(prev_effective_weights, new_eff_weights)
        prev_effective_weights = dict(new_eff_weights)
    elif self.transaction_cost > 0:
        # Phase 4 旧逻辑（method == "none" 时保持兼容）
        weight_turnover = sum(abs(pool_weights.get(k,0) - prev_pool_weights.get(k,0))
                              for k in set(pool_weights) | set(prev_pool_weights))
        scale_turnover = abs(effective_scale - prev_scale)
        cost = self.transaction_cost * (weight_turnover + scale_turnover) / 2
prev_scale = effective_scale
```

**向后兼容性**: `method == "none"` → `self.rebalancer = None` → 走 `elif` 分支，与 Phase 4 完全一致。`CalendarScheduler` 委托给 `BaseAllocator.get_rebalance_dates()`，调仓日不变。

## Implementation Order

1. `config_models.py` — RebalanceConfig 扩展（添加 cost_model 字段）
2. `execution/cost_model.py` — BaseCostModel + StockCostModel + ETFCostModel（无依赖）
3. `execution/base.py` — RebalanceResult + BaseRebalancer（无依赖）
4. `execution/rebalancer.py` — CostBenefitRebalancer 等（依赖 2、3）
5. `execution/scheduler.py` — CalendarScheduler + AdaptiveScheduler（依赖 engine.allocator）
6. `execution/executor.py` — SimulatedExecutor + LiveExecutor（无依赖）
7. `execution/__init__.py` — 模块导出（依赖 2-6）
8. `engine/backtest.py` — 集成修改（依赖 7）

## Verification

### 步骤 1: 插件注册验证
```python
import ohmyquant.execution
from ohmyquant.core.plugin_system import PluginRegistry, PluginType
assert "stock_cn" in PluginRegistry.list_plugins(PluginType.COST_MODEL)
assert "etf_cn" in PluginRegistry.list_plugins(PluginType.COST_MODEL)
assert "cost_benefit" in PluginRegistry.list_plugins(PluginType.REBALANCER)
assert "calendar" in PluginRegistry.list_plugins(PluginType.SCHEDULER)
```

### 步骤 2: 成本模型单元验证
```python
from ohmyquant.execution import create_cost_model
cm = create_cost_model({"name": "stock_cn"})
cost = cm.estimate({"A": 0.5, "B": 0.5}, {"A": 0.3, "C": 0.7})
# A 卖出 0.2 + B 卖出 0.5 + C 买入 0.7，验证数值合理
```

### 步骤 3: 调仓器单元验证
```python
from ohmyquant.execution import create_rebalancer
rb = create_rebalancer({"method": "cost_benefit", "cost_model": {"name": "stock_cn"}})
result = rb.decide({"A": 0.5, "B": 0.5}, {"A": 0.3, "C": 0.7},
                   hold_days_map={"A": 10, "B": 10},
                   scores={"A": 0.5, "B": 0.3, "C": 0.8})
assert result.need_rebalance and "B" in result.sells and "C" in result.buys
```

### 步骤 4: 调度器一致性验证
```python
from ohmyquant.execution import create_scheduler
from ohmyquant.engine.allocator import BaseAllocator
sched = create_scheduler({"frequency": "monthly"})
dates = ["2024-01-05", "2024-02-05", "2024-03-05"]
assert sched.get_rebalance_dates(dates) == BaseAllocator.get_rebalance_dates(dates, "monthly", 0)
```

### 步骤 5: Phase 4 回归测试（向后兼容）
```python
from ohmyquant.core.config_models import StrategyConfig
config = StrategyConfig()
config.rebalance.method = "none"  # 使用 flat cost
# 运行 Phase 4 端到端回测，验证净值曲线与 Phase 4 一致
```

### 步骤 6: 新功能集成验证
```python
config = StrategyConfig()
config.rebalance.method = "cost_benefit"
config.rebalance.cost_model = {"name": "stock_cn", "commission_rate": 0.0003}
# 运行回测，验证 exposure_log 中 transaction_cost 反映成本模型计算
```
