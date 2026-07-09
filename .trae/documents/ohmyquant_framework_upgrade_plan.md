# OhMyQuant 框架升级方案

## Context

OhMyQuant 已具备 7 策略 / 7 选股器 / 31 因子 / 4 模型 / 26 视图数据源，但存在三类阻碍其成为"完整可热插拔量化框架"的问题：

1. **仓库未治理**：未 git init、无 .gitignore、~130+ 个 `__pycache__/.pyc` 散落、3 个根目录临时脚本、8 个历史文档堆在 `.trae/documents/`。
2. **热插拔半成品**：中央 [PluginRegistry](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/plugin_system.py) 已支持 10 类插件的 `@register_*` 装饰器，但**发现机制是手写的**——每个插件包的 `__init__.py` 都靠 try/except 显式 import，新增插件必须改 `__init__.py`。[StrategyRunner._create_data_catalog](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/runner.py#L68-L92) 还硬编码了 `source_map`。[StrategyRegistry](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/registry.py) 与 [VersionManager](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/version_manager.py) 策略查找逻辑重复。
3. **功能与文档缺口**：[CLI list_command](file:///d:/Work/Project/OhMyQuant/ohmyquant/cli/commands.py#L150-L166) 的因子/数据源列表是**硬编码且错误**的（factors 显示 "alpha1, alpha5, alpha101"，实际是 31 个动量/反转等因子）；只支持 3 种列表类型；无优化/对比/信号/数据更新 CLI。无策略迭代操作手册。

**目标产出**：干净 git 仓库 + 零配置热插拔 + 完整文档 + 补全 CLI 工具链。策略本身的迭代（运行回测、产出效果）在框架升级后进行。

---

## Phase 1 — 仓库治理与清理 (Scope: M)

**目标**：建立干净版本控制基线。

1. 创建根 [.gitignore](file:///d:/Work/Project/OhMyQuant/.gitignore)：Python (`__pycache__/`, `*.pyc`, `*.egg-info/`, `.pytest_cache/`)、IDE (`.vscode/`, `.idea/`)、数据 (`data/`, `*.duckdb`, `*.parquet`)、输出 (`output/`, `results/`, `*.html`)、密钥 (`.env`, `credentials.json`)。
2. 删除全部 37 个 `__pycache__/` 目录 + `.pytest_cache/`（自动重建）。
3. 创建 `scripts/adhoc/`，移入 `check_data.py`、`run_ycj_test.py`；删除 `verify_nav_fix.py`（NAV bug 已修复，验证脚本过期）。
4. 创建 `docs/history/`，移入 `.trae/documents/` 下 8 个历史 Phase 文档（保留作历史档案）。README.md 保持为主入口文档。
5. `git init` + 首次提交 `chore: initialize repo with governance baseline`。

**风险**：.gitignore 必须在 `git add` 前存在，避免提交大数据/输出/密钥。提交前确认无敏感文件。

---

## Phase 2 — 热插拔自动发现改造 (Scope: L)

**目标**：零配置插件发现——把 `.py` 丢进对应包即自动注册。

### 2.1 新增发现工具
创建 [ohmyquant/core/discovery.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/discovery.py)：
- `discover_plugins(package_dir: Path, package_name: str) -> int`：用 `pkgutil.walk_packages` + `importlib.import_module` 扫描包目录，导入所有子模块以触发 `@register_*`。跳过 `__pycache__`/dunder，逐模块吞掉 `ImportError`（保留可选依赖行为）并 debug 日志。
- `PluginRegistry.discover_builtin()` classmethod：对内置插件包（strategies / factors.builtin / engine.selectors / engine.allocators / engine.risk_managers / data.sources / models.ml / models.dl / models.rl）统一调用 discover。用 `_discovered` 标志幂等。

### 2.2 改写 `__init__.py`（手写 import → discover）
- [strategies/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/__init__.py)：7 个 try/except → `discover_plugins(...)`
- [factors/builtin/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/__init__.py)
- [engine/selectors/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/__init__.py)（保留 `create_selector` 工厂）
- [engine/allocators/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/allocators/__init__.py)（保留 `create_allocator`）
- [engine/risk_managers/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/risk_managers/__init__.py)（保留 `create_risk_manager`）
- [data/sources/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/data/sources/__init__.py)
- [models/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/models/__init__.py) + `models/{ml,dl,rl}/__init__.py`（合并 `_register_builtin_models`）

### 2.3 收敛策略查找重复路径
- [version_manager.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/version_manager.py) `import_strategy_class`：先查 `PluginRegistry.get(PluginType.STRATEGY, f"{type}_{version}")`，命中即返回；未命中再 `importlib.import_module` 兜底（用于尚未注册的迭代版本）。
- [registry.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/registry.py) `get_strategy_class` 保持现状（已先查 PluginRegistry）。`StrategyRunner.run_strategy(strategy_type, version)` 公共 API **不变**。

### 2.4 修复硬编码数据源
[runner.py:68-92](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/runner.py#L68-L92) `_create_data_catalog`：删除 `source_map` 字典，改用 `PluginRegistry.create(PluginType.DATA_SOURCE, data_source_name, config={"data_root": data_root})`，`PluginNotFoundError` 时回退 `duckdb`。顺手修复 `runner.py:66` 引用未导入 `ExperimentTracker` 的 latent bug（改为 `Any` 或补 import）。

### 风险与对策
- **循环 import**：discover 导入 strategies/* → runner → registry → plugin_system。**对策**：discover 延迟执行——在 CLI `main()` 入口和 `StrategyRegistry.create` 内调用 `discover_builtin()`（幂等），不在包 import 时触发。
- **重依赖 eager load**：discover 会导入 torch/jqdatasdk（如已装）。可接受；逐模块 `ImportError` 吞掉保留可选依赖语义。
- **破坏 run_strategy API**：不改签名。

**复用**：`PluginRegistry.register/get/list_all/list_plugins`、`pkgutil.walk_packages`（stdlib）。

---

## Phase 3 — 策略迭代文档 (Scope: M)

**目标**：`docs/` 下补齐面向使用者的操作手册（基于 Phase 2 后的稳定状态）。

创建以下文件（绝对路径前缀 `d:\Work\Project\OhMyQuant\docs\`）：
1. `architecture.md` — 模块依赖图（CLI→Strategy→Engine→Factors/Models→Data）、热插拔机制（discover_plugins + PluginRegistry）、数据流。
2. `plugin_hotplug.md` — 如何新增任意插件类型：丢 `.py` 进对应包 + `@register_*` 装饰器 + 重启即生效。覆盖全部 10 种 PluginType，引用 discovery.py。
3. `factor_development.md` — [Factor ABC](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/base.py)、`@register_factor`、`compute()` 契约（返回 date×code polars 宽表）、`direction`/`required_fields`、用 [FactorAnalyzer](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/analysis.py) 做 IC/ICIR 分析。含完整示例。
4. `selector_development.md` — `BaseSelector`、`@register_selector`、`create_selector` 方法分派、icir/momentum/hybrid/ml/model/rl 适用场景对照。
5. `strategy_iteration_guide.md` — 复制 v1→v2 目录 → 编辑 config.yaml → 新增因子 → [StrategyWalkForward](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/walk_forward.py) 验证 → [ParamSearcher](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/param_search.py) 搜参 → [StrategyComparator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/compare.py) 对比 → [Ensemble](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/ensemble.py) 集成。引用 strategies/ 下真实路径。
6. `strategy_comparison.md` — StrategyComparator、[ReportGenerator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/report.py).generate_html_report、[SignificanceTester](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/significance.py) 显著性检验用法。
7. `rebalance_execution.md` — [CostModel](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/cost_model.py)、[Rebalancer](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/rebalancer.py) 方法、[Scheduler](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/scheduler.py)、[Executor](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/executor.py) 工作流。

**复用**：现有模块 docstring + 已迁移的 `docs/history/` 作背景。

---

## Phase 4 — 功能模块补全 (Scope: M)

**目标**：CLI 暴露全部插件类型 + 优化/对比/信号；单一数据更新脚本。

### 4.1 修复并扩展 `list_command`
[commands.py:150-166](file:///d:/Work/Project/OhMyQuant/ohmyquant/cli/commands.py#L150-L166)：调用 `PluginRegistry.discover_builtin()` 后 `PluginRegistry.list_all()`。支持 10 种类型：`strategies|factors|selectors|allocators|risk_managers|rebalancers|cost_models|data_sources|models`。`strategies` 额外用 `VersionManager.list_versions` 显示版本。
[cli/__init__.py:67](file:///d:/Work/Project/OhMyQuant/ohmyquant/cli/__init__.py#L67)：`choices` 扩到全部类型。

### 4.2 新增 CLI 子命令
在 [cli/__init__.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/cli/__init__.py) 增 subparser，在 [commands.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/cli/commands.py) 增对应函数：
- `optimize walk-forward <type> <version> [--window 1Y] [--step 1Y]` → 包装 [StrategyWalkForward](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/walk_forward.py)
- `optimize param-search <type> <version> --params <json>` → 包装 [ParamSearcher](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/param_search.py)
- `compare <r1.json> <r2.json> [--report out.html]` → 加载两 result JSON，用 [StrategyComparator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/compare.py) + [ReportGenerator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/report.py).generate_html_report 一键出 HTML 报告
- `signal <type> <version>` → `StrategyRegistry.create(...).get_latest_positions()`，打印 `{code: weight}`

### 4.3 修复 result JSON 持久化
[commands.py:46-52](file:///d:/Work/Project/OhMyQuant/ohmyquant/cli/commands.py#L46-L52) `run_command` 当前只存 `metrics`，未存 `daily_returns`。补存 `daily_returns` 数组，否则 `compare`/`report` 无收益序列可用。`backtest_command` 同步修复。

### 4.4 单一数据更新脚本
创建 [scripts/update_data.py](file:///d:/Work/Project/OhMyQuant/scripts/update_data.py)：T 日早晨下载 T-1 数据，当年全量 + 前一年（跨年应对，不传 YYYYMMDD 参数），经 [JQDataSource](file:///d:/Work/Project/OhMyQuant/ohmyquant/data/sources/jqdata_source.py)，**不抑制 jqdata warning**，与 `download_a_share` 数据目录布局对齐。凭据从环境变量 `JQ_USERNAME`/`JQ_PASSWORD` 读取。

### 风险
- `get_latest_positions()` 当前 7 个策略全返回 `{}`——`omq signal` 在策略迭代前输出空。文档明示此限制。
- `compare` 依赖 result JSON 含 `daily_returns`——4.3 是 4.2 compare 的前置小修。

**复用**：`StrategyWalkForward.run()`、`ParamSearcher.search()`、`StrategyComparator`、`ReportGenerator`、`JQDataSource`、`StrategyRegistry.create`。

---

## 验证

每阶段完成后验证：

- **Phase 1**：`git status` 干净；`Get-ChildItem -Recurse __pycache__` 无结果；`.gitignore` 存在。
- **Phase 2**：`python -m ohmyquant.cli list strategies` 显示 7 策略；`python -m ohmyquant.cli list factors` 显示 31 因子；`python -m ohmyquant.cli list selectors` 显示 7 选股器；新增一个空策略目录（仅 strategy.py + @register_strategy）后无需改 `__init__.py` 即可被 `list strategies` 发现；`pytest tests/` 全绿（30 passed）。
- **Phase 3**：`docs/` 下 7 个 md 存在；`strategy_iteration_guide.md` 含可执行步骤且路径有效。
- **Phase 4**：`omq list <type>` 全 10 类型可列；`omq optimize walk-forward ycj v1 --window 1Y` 可跑；`omq compare r1.json r2.json --report out.html` 生成 HTML；`python scripts/update_data.py --dry-run` 不报错。

## 顺序与依赖
Phase 1 (M) → Phase 2 (L) → Phase 3 (M) → Phase 4 (M)。Phase 3/4 均依赖 Phase 2；Phase 3 先于 Phase 4，因其文档化的是稳定模块 API 而非 CLI 接线。
