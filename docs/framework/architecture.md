# OhMyQuant 架构文档

## 概览

OhMyQuant 是一个模块化量化策略框架，集策略迭代、因子选股、回测、建仓调仓、策略对比于一体。所有可插拔组件通过中央注册表统一管理，支持零配置热插拔。

## 模块依赖图

```
CLI (cli/)
  └── Strategy (strategy/)
        ├── StrategyRunner → BacktestEngine (engine/)
        │     ├── Selector (engine/selectors/)    ← 因子驱动选股
        │     ├── RiskManager (engine/risk_managers/)  ← 波动率/回撤风控
        │     ├── Allocator (engine/allocator.py)  ← 等权/HRP/ICIR加权
        │     └── PortfolioOptimizer (engine/portfolio.py)
        ├── Factors (factors/)                    ← 31 个内置因子
        │     └── FactorAnalyzer (factors/analysis.py)  ← IC/ICIR 分析
        ├── Execution (execution/)                ← 调仓执行
        │     ├── CostModel (cost_model.py)       ← stock_cn/etf_cn/mixed_cn
        │     ├── Rebalancer (rebalancer.py)      ← cost_benefit/simple/none
        │     ├── Scheduler (scheduler.py)        ← calendar/adaptive
        │     ├── Executor (executor.py)          ← simulated/live
        │     └── ths_utils.py                    ← 同花顺交易文件生成(跨策略复用)
        ├── Optimization (optimization/)          ← 策略优化
        │     ├── StrategyWalkForward (walk_forward.py)
        │     ├── ParamSearcher (param_search.py) ← Optuna/网格搜索
        │     └── StrategyEnsemble (ensemble.py)  ← 多策略集成
        ├── Analysis (analysis/)                  ← 绩效分析
        │     ├── StrategyComparator (compare.py)
        │     ├── ReportGenerator (report.py)     ← HTML/Markdown 报告
        │     ├── SignificanceTester (significance.py)  ← t检验/Bootstrap/DSR
        │     └── metrics.py                      ← Sharpe/Sortino/Calmar 等
        └── Data (data/)                          ← 数据层
              ├── DataCatalog (base.py)           ← 统一数据访问
              ├── DuckDBSource (sources/duckdb_source.py)  ← 26 视图
              ├── CSVSource / LocalParquetSource
              └── Calendar (calendar.py) / Universe (universe.py)
```

## 热插拔机制

### 核心组件

- [discovery.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/discovery.py)：`discover_modules(package)` 使用 `pkgutil.walk_packages` + `importlib.import_module` 扫描包目录，导入所有子模块以触发 `@register_*` 装饰器。
- [plugin_system.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/plugin_system.py)：`PluginRegistry` 中央注册表，管理 9 种 PluginType。`discover_builtin()` 幂等方法导入 9 个内置插件包。

### 自动发现流程

```
import ohmyquant
  └── _load_builtin_plugins()
        └── PluginRegistry.discover_builtin()
              ├── import ohmyquant.data.sources       → __init__ 调用 discover_modules(__name__)
              ├── import ohmyquant.factors.builtin     → __init__ 调用 discover_modules(__name__)
              ├── import ohmyquant.engine.selectors    → __init__ 调用 discover_modules(__name__)
              ├── import ohmyquant.engine.allocators   → __init__ 调用 discover_modules(__name__)
              ├── import ohmyquant.engine.risk_managers → __init__ 调用 discover_modules(__name__)
              ├── import ohmyquant.execution.cost_model
              ├── import ohmyquant.execution.scheduler
              ├── import ohmyquant.execution.rebalancer
              └── import ohmyquant.strategy.strategies  → __init__ 调用 discover_modules(__name__)
```

每个包的 `__init__.py` 调用 `discover_modules(__name__)`，扫描自身子模块。新增插件只需把 `.py` 文件放进对应包，无需修改任何 `__init__.py`。

### 9 种 PluginType

| 类型 | 装饰器 | 包路径 |
|------|--------|--------|
| FACTOR | `@register_factor("name", category="...")` | `factors/builtin/` |
| SELECTOR | `@register_selector("name")` | `engine/selectors/` |
| ALLOCATOR | `@register_allocator("name")` | `engine/allocators/` |
| RISK_MANAGER | `@register_risk_manager("name")` | `engine/risk_managers/` |
| REBALANCER | `@register_rebalancer("name")` | `execution/rebalancer.py` |
| COST_MODEL | `@register_cost_model("name")` | `execution/cost_model.py` |
| SCHEDULER | `@register_scheduler("name")` | `execution/scheduler.py` |
| DATA_SOURCE | `@register_data_source("name")` | `data/sources/` |
| STRATEGY | `@register_strategy("type", "version")` | `strategy/strategies/` |

## 数据流

```
DuckDB (26 视图)
  ↓ DuckDBSource.get_*()
DataCatalog (data/base.py)
  ↓ 宽表 polars DataFrame (date × code)
BacktestEngine.run()
  ↓ 按调仓日循环
  ├── Factor.compute() → 因子值矩阵
  ├── Selector.select() → {code: weight}
  ├── RiskManager.apply() → 调整后权重
  ├── Allocator.allocate() → 最终权重
  ├── Rebalancer.decide() → 调仓决策
  └── CostModel.estimate() → 交易成本
  ↓
BacktestResult (daily_returns, nav, metrics, pool_weight_log)
  ↓
Analysis (metrics / compare / report / significance)
```

## 策略版本管理

策略目录结构：
```
strategy/strategies/
└── industry_rotation/
    ├── v4/
    │   ├── __init__.py
    │   ├── config.yaml
    │   └── strategy.py      ← @register_strategy("industry_rotation", "v4")
    └── v66/
        ├── __init__.py
        ├── config.yaml
        └── strategy.py      ← @register_strategy("industry_rotation", "v66")
```

[VersionManager](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/version_manager.py) 支持迭代版本（如 v2.1）：
```
strategies/industry_rotation/v66/
  ├── config.yaml
  └── strategy.py
```

策略查找优先级：`PluginRegistry.get(STRATEGY, "industry_rotation_v66")` → `importlib.import_module`（兜底）。
