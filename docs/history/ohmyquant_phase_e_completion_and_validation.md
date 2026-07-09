# OhMyQuant Phase E 收尾 + 全量验证 + 能力提升方案

## Summary

本次任务收尾上一轮迭代：补齐 `ohmyquant/optimization/` 缺失的 3 个文件（`walk_forward.py` / `param_search.py` / `ensemble.py`），修复当前 optimization 模块的 import 断裂；随后执行全量验证（pytest + ycj/ETF/ML 端到端试运行），确认无回归并记录暴露问题；最后产出一份《框架能力提升方案》分析文档，对标主流框架、覆盖用户提出的 4 个强化方向。

**不新增超出原 Phase E 计划的功能模块**——额外增强项仅以方案形式记录，不在本次实现。

---

## Current State Analysis

### 已完成（上一轮）
- **Phase A**: NAV Bug 修复（backtest.py 起点归一化为 1.0）
- **Phase B**: DuckDBSource 扩展 22 视图 + 6 个加载方法（财务报表/龙虎榜/北向/限售/因子宽表/指数成分），`union_by_name` 处理跨年 schema，`statDate` 修复
- **ycj 试运行**: 已跑通，484 天，final_nav=1.1748，Sharpe 0.5247，NAV 一致性检查 PASS
- **Phase C**: ML/DL/RL 统一框架（Model ABC + FeaturePipeline + TrainingPipeline + WalkForwardRunner + 5 个模型插件 lightgbm_ltr/xgboost_ltr/mlp/lstm/ppo_portfolio + ModelSelector）
- **Phase D**: ETF 支持（MixedCostModel + etf v1 轮动 + etf v2 混合策略）

### 当前断裂点
- `ohmyquant/optimization/__init__.py` 已导入 `StrategyWalkForward` / `WalkForwardReport` / `ParamSearcher` / `OptimizationReport` / `StrategyEnsemble` / `EnsembleResult`，但对应 3 个源文件**不存在** → `from ohmyquant.optimization import ...` 直接 ImportError
- 幸运：`ohmyquant/__init__.py` 未导入 optimization，`tests/` 也未导入 optimization，故单元测试目前不受影响，但 optimization 模块本身完全不可用

### 关键接口（已通过 Phase 1 探查确认）
- **StrategyRunner.run_strategy(strategy_type, version, config_overrides=None) → StrategyResult**（[runner.py:148](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/runner.py#L148)）；`StrategyResult.backtest_result: BacktestResult`、`config: StrategyConfig`
- **BacktestResult**（[engine/base.py:13](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/base.py#L13)）：`nav: pl.Series`、`dates: list[str]`、`daily_returns: pl.Series | None`、`final_nav`、`n_days` 属性
- **compute_metrics(returns, benchmark_returns=None) → PerformanceMetrics**（[analysis/metrics.py:237](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/metrics.py#L237)）；另有 `compute_sharpe_ratio` / `compute_info_ratio` / `compute_max_drawdown`
- **VersionManager.load_config(strategy_type, version) → dict**（[version_manager.py:161](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/version_manager.py#L161)）加载 yaml 基础配置
- **StrategyConfig** 子配置可调参项：`selection.top_n`(1-500) / `selection.max_stock_weight` / `selection.ic_decay` / `selection.icir_window` / `risk.target_vol` / `rebalance.frequency` / `backtest.transaction_cost` / `factors`
- **models/walk_forward.py 的 WalkForwardRunner** 是模型级（train/test 窗口），本次 `optimization/walk_forward.py` 是**策略级**（连续测试窗口评估跨期稳定性），职责不同，不冲突

### 数据兼容性结论（上一轮已验证，本次复用）
download_a_share 的 27 个 parquet 子目录全部可通过 DuckDBSource 访问，schema 不一致已由 `union_by_name` 解决。本次不重复数据层改动，仅在验证阶段重跑确认无回归。

---

## Proposed Changes

### Step 1: 创建 `ohmyquant/optimization/walk_forward.py`（策略级 walk-forward）

**职责**: 将回测区间切分为连续测试窗口，每个窗口独立运行策略，评估绩效跨周期一致性。

**核心类**:
```python
@dataclass
class WindowResult:
    window_idx: int
    start_date: str
    end_date: str
    metrics: PerformanceMetrics
    final_nav: float

@dataclass
class WalkForwardReport:
    strategy_type: str
    version: str
    windows: list[WindowResult]
    mean_sharpe: float
    std_sharpe: float
    mean_annual_return: float
    positive_windows: int      # sharpe > 0 的窗口数
    consistency: float         # positive_windows / total
    def summary(self) -> str: ...

class StrategyWalkForward:
    def __init__(self, test_window: str = "1Y", step: str = "1Y"):
        # 解析 "1Y"->252, "6M"->126, "63D"->63
    def run(self, strategy_type, version, base_overrides=None) -> WalkForwardReport:
        # 1. 用 base_overrides 全程跑一次，拿到 backtest_result.dates（交易日历）
        # 2. 按 test_window/step 切分 dates 为连续窗口
        # 3. 每个窗口：override backtest.start_date/end_date，run_strategy，compute_metrics(daily_returns)
        # 4. 聚合 mean/std/consistency
```

**设计决策**:
- 用"先全程跑一次拿日期，再按窗口重跑"的方式获取交易日历，避免直接耦合数据层（robust 但 N+1 次回测，作为 v1 已知成本，分析文档中记录）
- 窗口 spec 用字符串解析，避免复杂日期算术
- 复用 `StrategyRunner.run_strategy` + `compute_metrics`，不重造轮子

### Step 2: 创建 `ohmyquant/optimization/param_search.py`（Optuna 参数搜索）

**职责**: 策略超参搜索。Optuna 可用时贝叶斯优化，不可用时降级网格搜索。

**核心类**:
```python
@dataclass
class TrialResult:
    params: dict[str, Any]
    value: float
    metrics: dict[str, float]

@dataclass
class OptimizationReport:
    strategy_type: str
    version: str
    metric: str
    best_params: dict[str, Any]
    best_value: float
    best_metrics: dict[str, float]
    n_trials: int
    trials: list[TrialResult]
    backend: str  # "optuna" / "grid"
    def summary(self) -> str: ...

class ParamSearcher:
    def __init__(self, n_trials=50, metric="sharpe", direction="maximize"): ...
    def search(self, strategy_type, version, param_space) -> OptimizationReport:
        # param_space: {"selection.top_n": {"type":"int","low":10,"high":100,"step":10},
        #               "risk.target_vol": {"type":"float","low":0.1,"high":0.4},
        #               "rebalance.frequency": {"type":"categorical","choices":["monthly","weekly"]}}
```

**设计决策**:
- `try import optuna`，不可用时 `_HAS_OPTUNA=False`，降级为 `itertools.product` 网格搜索（int/float 用 step 离散化，categorical 全枚举）
- 配置合并：`VersionManager.load_config` 取基础 yaml → `_apply_flat_params` 将 `"selection.top_n"` 形式的扁平参数深合并到嵌套 dict → 作为 `config_overrides` 传给 `run_strategy`（因 `StrategyRegistry.create` 用 `base_config.update(config)`，传入完整嵌套 dict 会整体替换，符合预期）
- 目标函数：`_evaluate` 跑策略 → 取 `daily_returns` → `compute_sharpe_ratio`（或按 metric 选 total_return/max_drawdown）
- 网格规模过大时（>n_trials）随机采样截断，并 warning

### Step 3: 创建 `ohmyquant/optimization/ensemble.py`（多策略集成）

**职责**: 将多个策略的日收益序列按权重组合，输出集成净值与绩效。

**核心类**:
```python
@dataclass
class EnsembleResult:
    weighting: str
    nav: list[float]
    dates: list[str]
    metrics: PerformanceMetrics
    constituents: list[dict]  # [{strategy_type, version, weight, metrics}]

class StrategyEnsemble:
    def __init__(self, weighting="equal", benchmark_returns=None): ...
    def add_strategy(self, strategy_type, version, weight=1.0): ...
    def run(self, config_overrides=None) -> EnsembleResult:
        # 1. 逐个 run_strategy 成分策略
        # 2. 取各自 daily_returns + dates，按日期交集对齐
        # 3. 计算权重（equal/perf_weight/ir_weight）
        # 4. combined_returns = Σ w_i * returns_i
        # 5. nav = cumprod(1+combined_returns)，归一化起点 1.0
        # 6. compute_metrics(combined_returns)
```

**权重方式**:
- `equal_weight`: 1/N
- `perf_weight`: w_i ∝ max(sharpe_i, 0)，全 ≤0 则退化为等权
- `ir_weight`: w_i ∝ max(ir_i vs benchmark, 0)，需 `benchmark_returns`，缺失则 warning + 退化 perf_weight

**对齐策略**: 用日期交集（`set.intersection`），缺失日该策略收益按 0 填充；保证所有成分在同一日期轴上加权。

### Step 4: 全量验证

1. **import 修复确认**: `python -c "from ohmyquant.optimization import StrategyWalkForward, ParamSearcher, StrategyEnsemble; print('ok')"`
2. **单元测试**: `pytest tests/ -v`，确认 30 passed（上一轮基线）无回归
3. **ycj v1 端到端**: 运行 `scripts/run_ycj_smoke.py`，确认 final_nav/Sharpe 与上一轮量级一致，NAV[0]=1.0
4. **ETF v1 烟雾测试**: 新建 `scripts/run_etf_smoke.py`，跑 etf v1 轮动（2023-2024），确认 ETFCostModel 生效、调仓正常
5. **ML/ModelSelector 烟雾测试**: 新建 `scripts/run_ml_smoke.py`，跑 ycj v1 + `selection.method=model` + `selection.model_name=lightgbm_ltr`（lightgbm 未装则跳过并记录）；若装了则确认训练/推理走通
6. **optimization 功能测试**: 新建 `scripts/run_optimization_smoke.py`，跑 `StrategyEnsemble(ycj v1 + etf v1)` 与 `StrategyWalkForward('ycj','v1')` 小窗口，确认不报错、产出 report

所有烟雾脚本放 `scripts/`，验证完成后记录暴露问题（性能/异常/功能缺失）到分析文档。

### Step 5: 产出《框架能力提升方案》分析文档

**文件**: `.trae/documents/ohmyquant_capability_upgrade_plan.md`

**内容大纲**:
1. **迭代过程梳理**: Phase 1-10 + A-E 完成情况总览
2. **遗漏环节与潜在问题**: 验证阶段实测发现的问题清单（含 optimization N+1 回测成本、网格搜索规模、对齐填充假设等）
3. **数据兼容性评估**: download_a_share 27 子目录利用情况、未利用数据、增量更新兼容性
4. **ycj/ETF/ML 试运行记录**: 指标、暴露的功能缺失/性能瓶颈/异常
5. **对标主流框架**: 对比 backtrader / vnpy / zipline / qlib / bt，列出已具备与尚缺能力矩阵
6. **能力提升方案**（对应用户 4 点要求）:
   - A股+ETF 全覆盖：现状（已支持）+ 待补（可转债/国债期货/期权/港股通）
   - download_a_share 数据充分利用：现状（22 视图）+ 未利用数据（概念板块/融资融券明细/分笔）+ 建议
   - 传统/ML/DL/RL 统一环境：现状（5 模型插件 + ModelSelector + Signal）+ 待补（模型对比/A-B 测试/自动调参记录/特征库）
   - 模块化可扩展架构：现状（9+1 插件类型）+ 待补（事件驱动引擎/组合优化器/实盘对接/参数版本化/回测加速）
7. **优先级建议**: P0/P1/P2 分级，标注哪些是"方案仅"、哪些可后续迭代实现

---

## Assumptions & Decisions

1. **不新增超出 Phase E 的功能模块**——用户已确认本次范围为"完成 Phase E + 验证 + 分析"，额外增强仅以方案形式记录
2. **walk-forward 用 N+1 回测**换取实现简洁与健壮性，作为 v1 已知性能成本，分析文档中明确记录并提出优化方向（直接查交易日历）
3. **Optuna 可选**：try import，缺失降级网格搜索，不强制安装
4. **ensemble 收益对齐用日期交集**，缺失日填 0（假设该日无持仓），这是保守假设，文档中说明
5. **ML 烟雾测试依赖 lightgbm**：若未安装则跳过并记录，不阻断验证流程（DL/RL 依赖 PyTorch/SB3 同理）
6. **复用现有 runner/metrics**：3 个新文件均调用 `StrategyRunner.run_strategy` 与 `compute_metrics`，不重造回测/指标逻辑
7. **配置深合并**：param_search 用 `_apply_flat_params` 将 `"a.b.c"` 扁平参数合并进 yaml 基础配置的嵌套 dict

---

## Verification Steps

1. `from ohmyquant.optimization import StrategyWalkForward, ParamSearcher, StrategyEnsemble` 无 ImportError
2. `pytest tests/ -v` 全部通过（≥ 30 passed，无新增失败）
3. `scripts/run_ycj_smoke.py` 跑通，final_nav 量级合理（0.9-1.3），NAV[0]=1.0
4. `scripts/run_etf_smoke.py` 跑通，ETF 池走 ETFCostModel，调仓日志非空
5. `scripts/run_ml_smoke.py`：lightgbm 已装则训练/推理走通；未装则优雅跳过并记录
6. `scripts/run_optimization_smoke.py`：StrategyEnsemble 产出合并净值；StrategyWalkForward 产出 ≥2 窗口 report
7. `.trae/documents/ohmyquant_capability_upgrade_plan.md` 生成，覆盖 7 大纲
