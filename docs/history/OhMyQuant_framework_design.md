# OhMyQuant 综合性量化框架 - 实现计划

## Context

用户需要在 `d:\Work\Project\OhMyQuant`（当前空目录）从零构建一个集量化策略迭代、回测分析、建仓调仓、因子开发与迭代、策略插件系统于一体的综合性量化框架。

融合三个参考代码库的精华：
- **halo_index**（主要架构）：统一策略入口 `Strategy.from_version().run()`、可插拔选股器（BaseSelector + ICIR/ML/Hybrid/Adaptive）、多池回测引擎、YAML 版本化配置
- **ETF_portfolio**（次要架构）：frozen dataclass 参数、版本注册表（主版本/迭代版本）、成本收益权衡调仓模型
- **download_a_share**（数据层）：聚宽 API、Parquet+DuckDB 存储、22+数据类型、增量更新、宽表构建

技术栈升级：Pydantic v2（配置校验）+ polars（数据处理）+ OmegaConf（层次化配置）+ Typer（CLI）+ Plotly（可视化）+ loguru（日志）。

README 需包含 slogan：`OhMyQuant — Because quant trading shouldn't be a headache. Plugins, backtesting, factors, and rebalancing, all in one swoop.`

## 架构总览

插件化架构，所有可插拔组件（策略/因子/选股器/风控/分配器/调仓器/数据源）通过统一注册系统管理。三层配置合并（全局默认 → 策略版本 → 运行时覆盖）+ Pydantic v2 校验。

## 目录结构

```
OhMyQuant/
├── pyproject.toml                          # 依赖、entry points、工具链
├── README.md                               # 含 slogan
├── .env.example                            # JQ 凭证模板
├── .gitignore
├── Makefile
├── ohmyquant/                              # 主包
│   ├── __init__.py                         # 公共 API 导出
│   ├── core/                               # 核心基础设施
│   │   ├── plugin_system.py                # 插件注册表 + 装饰器 + entry_points 发现
│   │   ├── config_manager.py               # OmegaConf 层次化配置（三层合并）
│   │   ├── config_models.py                # Pydantic v2 配置模型（校验）
│   │   ├── logging.py                      # loguru 日志
│   │   ├── exceptions.py                   # 统一异常体系
│   │   ├── cache.py                        # LRU/磁盘缓存
│   │   ├── parallel.py                     # 线程池/进程池
│   │   └── types.py                        # 公共类型
│   ├── data/                               # 数据抽象层（全新设计，兼容 download_a_share）
│   │   ├── base.py                         # DataSource ABC + DataCatalog
│   │   ├── sources/                        # 可插拔数据源
│   │   │   ├── jqdata_source.py            # 聚宽（在线下载）
│   │   │   ├── local_parquet_source.py     # 本地 Parquet（兼容现有数据）
│   │   │   ├── duckdb_source.py            # DuckDB 视图查询
│   │   │   └── csv_source.py              # 测试用
│   │   ├── downloaders/                    # 下载器
│   │   │   ├── base_downloader.py
│   │   │   └── jq_downloader.py            # 22+数据类型下载
│   │   ├── storage/                        # 存储管理
│   │   │   ├── parquet_store.py            # 分区 Parquet
│   │   │   ├── duckdb_store.py             # DuckDB 宽表
│   │   │   └── wide_table_builder.py       # 宽表构建
│   │   ├── updater.py                      # T日下载T-1工作流
│   │   ├── universe.py                     # 股票池/ETF池
│   │   └── calendar.py                     # 交易日历
│   ├── factors/                            # 因子平台
│   │   ├── base.py                         # Factor ABC + FactorRegistry
│   │   ├── builtin/                        # 内置因子（momentum/reversal/volatility/valuation/...）
│   │   ├── analysis.py                     # IC/ICIR/分位数/衰减分析
│   │   ├── testing.py                      # 因子测试工作流
│   │   ├── optimizer.py                    # 因子组合优化
│   │   └── library.py                      # 因子库管理
│   ├── engine/                             # 回测引擎
│   │   ├── base.py                         # BaseEngine ABC
│   │   ├── backtest.py                     # BacktestEngine（向量化多池）
│   │   ├── context.py                      # BacktestContext
│   │   ├── selector.py                     # BaseSelector ABC
│   │   ├── selectors/                      # icir/ml/hybrid/adaptive
│   │   ├── risk.py                         # BaseRiskManager ABC
│   │   ├── risk_managers/                  # vol_target/cvar/drawdown/regime_adaptive
│   │   ├── allocator.py                    # BaseAllocator ABC
│   │   ├── allocators/                     # equal/hrp/icir_weighted
│   │   └── portfolio.py                    # PortfolioOptimizer
│   ├── execution/                          # 调仓执行
│   │   ├── base.py                         # BaseRebalancer ABC
│   │   ├── rebalancer.py                   # 成本收益权衡调仓
│   │   ├── cost_model.py                   # 交易成本（股票/ETF）
│   │   ├── scheduler.py                    # 调仓频率（日/周/月/自适应）
│   │   └── executor.py                     # 模拟/实盘接口
│   ├── strategy/                           # 策略系统
│   │   ├── base.py                         # BaseStrategy ABC
│   │   ├── registry.py                     # 版本注册表（lru_cache）
│   │   ├── runner.py                       # 统一运行入口
│   │   └── version_manager.py              # 主版本/迭代版本管理
│   ├── strategies/                         # 策略实现
│   │   ├── ycj/v1/{config.yaml,strategy.py}
│   │   ├── ycj/v2/{config.yaml,strategy.py}
│   │   ├── ycj/v2/iterations/v2_1/         # 迭代版本
│   │   └── dh/v1/{config.yaml,strategy.py}
│   ├── analysis/                           # 分析
│   │   ├── metrics.py                      # 绩效指标
│   │   ├── compare.py                      # 多策略对比
│   │   ├── significance.py                 # 统计显著性（t检验/Bootstrap/DSR）
│   │   ├── attribution.py                  # 归因
│   │   └── report.py                       # 报告生成
│   ├── visualization/                      # Plotly 可视化
│   │   ├── plots.py                        # 净值/回撤/权重/IC 图
│   │   ├── dashboard.py                    # 交互仪表盘
│   │   └── themes.py
│   ├── tracking/                           # 实验追踪
│   │   ├── tracker.py                      # 实验记录
│   │   └── storage.py                      # Parquet 存储
│   ├── integration/                        # 外部集成
│   │   ├── broker.py                       # 券商接口抽象
│   │   ├── notification.py                 # 通知
│   │   └── export.py                       # 数据导出
│   └── cli/                                # Typer CLI
│       ├── main.py                         # 主入口
│       ├── data_cli.py / factor_cli.py / backtest_cli.py / strategy_cli.py / analysis_cli.py
├── config/                                 # 全局配置
│   ├── global_defaults.yaml
│   ├── pools.yaml
│   ├── data_sources.yaml
│   └── logging.yaml
├── tests/                                  # pytest 测试
│   ├── unit/ integration/ fixtures/
├── scripts/                                # 入口脚本
├── docs/                                   # 文档
└── outputs/                                # 输出（.gitignore）
```

## 关键设计

### 1. 插件系统 (`core/plugin_system.py`)
- `PluginType` 枚举：STRATEGY/FACTOR/SELECTOR/RISK_MANAGER/ALLOCATOR/REBALANCER/DATA_SOURCE/COST_MODEL
- `PluginRegistry` 类级单例：`register()` 装饰器注册、`get()` 获取、`create()` 实例化（自动 Pydantic 校验配置）、`discover()` 通过 entry_points 发现外部插件
- 便捷装饰器：`@register_factor("mom_1m", category="momentum")`、`@register_selector("icir")` 等
- `PluginLifecycle` 接口（可选）：initialize/configure/health_check/cleanup

### 2. 配置系统 (`core/config_manager.py` + `config_models.py`)
- 三层合并：`config/global_defaults.yaml` → `strategies/ycj/v2/config.yaml` → 运行时 dict 覆盖
- OmegaConf 做深合并 + 变量解析（`${...}`）
- Pydantic v2 模型校验：`StrategyConfig` 包含 `BacktestConfig`/`SelectionConfig`/`RiskConfig`/`AllocationConfig`/`PortfolioConfig`/`DataConfig`，带 `model_validator` 做跨字段校验（如 top_n × max_stock_weight 仓位检查）
- `ConfigManager.build_config(strategy_type, version, overrides)` 返回校验后的 `StrategyConfig`

### 3. 数据抽象层 (`data/base.py`)
- `DataSource` ABC：`load_daily_price/load_valuation/load_money_flow/load_margin/load_industry_map/load_index_data/get_trade_calendar/get_latest_date/filter_tradable/build_ohlcv_matrices`
- `DataCatalog`：统一访问入口 + 内存缓存 + 磁盘缓存
- 实现：
  - `LocalParquetSource`：直接读取 download_a_share 的 Parquet，兼容 `stock_daily_wide_partitioned` 目录结构，支持未复权/后复权字段切换
  - `DuckDBSource`：DuckDB SQL 视图查询 Parquet（谓词下推，性能优），Arrow→polars 零拷贝
  - `JQDataSource`：聚宽在线下载，凭证从环境变量读取
- `DataUpdater.run_daily_update()`：自动确定 T-1 日期（无需指定 YYYYMMDD），增量下载→重建当年宽表分区→更新因子→备份

### 4. 因子平台 (`factors/`)
- `Factor` ABC：`name/category/direction/required_fields` 元数据 + `compute(data) -> DataFrame` 抽象方法
- `FactorRegistry`：基于 PluginRegistry，`register/get/create/list_factors`
- 内置因子：momentum（mom_1m/mom_3m）、reversal（rev_5d）、volatility、valuation、money_flow、technical、sentiment
- `FactorAnalyzer`：compute_ic（Spearman/Pearson）、compute_icir（指数衰减加权）、compute_quantile_returns、compute_ic_decay
- `FactorTester`：完整测试工作流（加载→计算→IC分析→分位数→衰减→报告）
- `FactorOptimizer`：select_strong_factors（IC/ICIR 过滤 + 相关性去冗余）

### 5. 回测引擎 (`engine/backtest.py`)
- `BacktestEngine`：多池结构，通过 PluginRegistry 创建可插拔组件（selector/risk_manager/allocator）
- `run(pools, start_date, end_date)` 流程：加载数据→计算因子→计算前向收益→IC分析+强因子筛选→选股→回测主循环（调仓日检查→池间权重分配→风控暴露度→组合日收益→交易成本→净值更新）
- 选股器：`ICIRSelector`/`MLSelector`(LightGBM LTR)/`HybridSelector`(ICIR初筛+ML重排)/`AdaptiveICIRSelector`
- 风控：`RegimeAdaptiveRiskManager`（波动率目标+CVaR+市场状态检测+尾部风险）
- 分配器：`EqualAllocator`/`HRPAllocator`/`ICIRWeightedAllocator`
- `PortfolioOptimizer`：个股/行业权重上限约束

### 6. 调仓系统 (`execution/`)
- `CostBenefitRebalancer`：评估每个卖出候选的成本vs预期收益提升，仅净收益为正时调仓，跳过成本过高的调仓
- `CostModel`：股票（佣金+印花税+过户费）/ETF（申购费+赎回费，7天内惩罚性费率）
- `RebalanceScheduler`：日/周/月/季/自适应频率，自适应模式根据市场状态动态调整

### 7. 策略系统 (`strategy/`)
- `BaseStrategy` ABC：`from_version()/run()/get_latest_positions()/get_config_summary()`
- `StrategyRegistry`：`get_strategy_class(strategy_type, version)` with lru_cache，`register_strategy()` 运行时注册
- `VersionManager`：动态导入 `ohmyquant.strategies.{type}.{version}.strategy`，支持迭代版本 `v2.1` → `v2/iterations/v2_1/`
- YCJ_strategy v2 示例：参考 halo_index 的 hybrid 选股 + 多池结构

### 8. 分析与对比 (`analysis/`)
- `compute_metrics()`：年化收益/波动率/Sharpe/Sortino/Calmar/最大回撤/Info Ratio
- `StrategyComparator.compare()`：多策略指标对比表 + 滚动相关性 + 两两组合扫描
- `SignificanceTester`：t检验超额收益、Bootstrap Sharpe 置信区间、Deflated Sharpe Ratio（多重检验校正）

### 9. 可视化 (`visualization/plots.py`)
- Plotly 交互图：净值曲线、回撤、权重堆叠、因子IC、分位数收益
- `export_html()` 导出交互式 HTML

### 10. CLI (`cli/main.py`, Typer)
- `run_backtest --strategy ycj --version v2`
- `update_data`（T日下载T-1）
- `test_factor --factor-name mom_1m`
- `compare --strategies ycj:v2,dh:v1`

## 实现顺序（10 个 Phase）

1. **Phase 1 - 核心基础设施**：`core/plugin_system.py` → `config_manager.py` → `config_models.py` → `logging.py` → `exceptions.py` → `cache.py` → `parallel.py` → `types.py`
2. **Phase 2 - 数据层**：`data/base.py` → `sources/*` → `storage/*` → `downloaders/*` → `calendar.py` → `universe.py` → `updater.py`
3. **Phase 3 - 因子平台**：`factors/base.py` → `builtin/*` → `analysis.py` → `testing.py` → `optimizer.py` → `library.py`
4. **Phase 4 - 回测引擎**：`engine/base.py` → `context.py` → `selector.py` → `selectors/*` → `risk.py` → `risk_managers/*` → `allocator.py` → `allocators/*` → `portfolio.py` → `backtest.py`
5. **Phase 5 - 调仓执行**：`execution/cost_model.py` → `base.py` → `rebalancer.py` → `scheduler.py` → `executor.py`
6. **Phase 6 - 策略系统**：`strategy/base.py` → `version_manager.py` → `registry.py` → `runner.py` → `strategies/ycj/v1/*` → `strategies/ycj/v2/*` → `strategies/dh/v1/*`
7. **Phase 7 - 分析可视化**：`analysis/metrics.py` → `compare.py` → `significance.py` → `attribution.py` → `report.py` → `visualization/plots.py` → `dashboard.py`
8. **Phase 8 - 追踪集成**：`tracking/*` → `integration/*`
9. **Phase 9 - CLI 脚本**：`cli/*` → `scripts/*`
10. **Phase 10 - 测试文档**：`tests/*` → `docs/*` → `README.md` → `pyproject.toml`

## 关键文件（按优先级）

1. `ohmyquant/core/plugin_system.py` - 插件注册系统，所有可插拔组件的基础
2. `ohmyquant/core/config_manager.py` - 层次化配置管理，OmegaConf + Pydantic v2 整合
3. `ohmyquant/data/base.py` - DataSource ABC + DataCatalog，数据抽象层核心
4. `ohmyquant/engine/backtest.py` - BacktestEngine，整合选股/风控/分配/组合优化
5. `ohmyquant/strategy/base.py` - BaseStrategy ABC，连接配置/数据/引擎的枢纽

## 复用的参考代码

- halo_index `src/engine/strategy.py` → `ohmyquant/strategy/base.py` 的 `from_version()/run()/get_latest_positions()` 模式
- halo_index `src/engine/selectors.py` → `ohmyquant/engine/selectors/*` 的 ICIR/ML/Hybrid/Adaptive 实现
- halo_index `src/engine/config_loader.py` → `ohmyquant/core/config_manager.py` 的三层合并 + flatten + validate 模式
- ETF_portfolio `strategy/registry.py` → `ohmyquant/strategy/registry.py` 的 lru_cache + 主版本/迭代版本
- ETF_portfolio `strategy/execution/rebalancer.py` → `ohmyquant/execution/rebalancer.py` 的成本收益权衡模型
- ETF_portfolio `strategy/params.py` → `ohmyquant/core/config_models.py` 的 Pydantic 参数模型
- download_a_share `config.py` → `ohmyquant/data/sources/jqdata_source.py` 的字段定义和数据类型

## 验证方案

1. **单元测试**：每个模块的核心类有对应 `tests/unit/test_*.py`，用 `pytest` 运行
2. **端到端测试**：`tests/integration/test_end_to_end.py` 运行 `YCJ_strategy_v1` 完整回测，验证净值曲线生成
3. **数据兼容性测试**：`tests/integration/test_data_workflow.py` 验证 LocalParquetSource 能正确读取 `D:/Work/Project/download_a_share/data`
4. **CLI 验证**：`python -m ohmyquant.cli.main run_backtest --strategy ycj --version v2`
5. **因子测试验证**：`python -m ohmyquant.cli.main test_factor --factor-name mom_1m`，验证 IC/ICIR 输出合理
6. **策略对比验证**：`python -m ohmyquant.cli.main compare --strategies ycj:v1,ycj:v2`，验证对比报告生成
