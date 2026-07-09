# OhMyQuant 框架全面迭代计划

## 背景

框架已完成 Phase 1-10 基础建设，ycj 策略已成功跑通全流程（数据加载→因子计算→IC分析→选股→回测→绩效指标），验证了与 `D:\Work\Project\download_a_share` 数据的兼容性（5512只股票、1694只ETF、260因子，2005-2026）。

但试运行暴露以下关键缺口：
1. ML/DL/RL 支持不足（仅有 LightGBM LTR）
2. 数据利用率低（22类数据仅用了6类）
3. 无 ETF 策略模板
4. NAV 计算有 Bug（预热期收益被包含在 final_nav 中）
5. 无参数优化和策略集成框架

本计划按5个优先级分阶段解决，目标是打造支持传统/ML/DL/RL策略、覆盖A股+ETF、可快速迭代的量化框架。

---

## Phase A: NAV Bug 修复（最先执行）

**问题**: [backtest.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py) 第548行 `nav_list=[1.0]` 从 `data_start_date` 开始累积，但第706行 `nav_array = nav_list[bt_start_idx:]` 未归一化，导致 `final_nav` 包含预热期收益。`daily_returns_list` 也有偏移错位。

**修改文件**: `ohmyquant/engine/backtest.py`（第706-720行附近）
- 归一化：`nav_array = [v / nav_raw[0] for v in nav_raw]`
- 对齐：`daily_returns_bt = daily_returns_list[bt_start_idx:]`

**验证**: 回测起点 NAV 必须为 1.0，`len(daily_returns) == len(dates) - 1`

---

## Phase B: 数据能力增强

**修改文件**:
- [duckdb_source.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/data/sources/duckdb_source.py) — `_create_views`（第61-89行）新增13类数据视图，新增6个加载方法
- [base.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/data/base.py) — `DataSource` ABC 新增抽象方法，`DataCatalog` 新增代理方法
- [csv_source.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/data/sources/csv_source.py) / [local_parquet_source.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/data/sources/local_parquet_source.py) — 提供空实现

**新增数据加载方法**:
- `load_financial_statement(statement_type, codes, ...)` — 利润表/资产负债表/现金流/财务指标
- `load_billboard(codes, ...)` — 龙虎榜数据
- `load_hk_holdings(codes, ...)` — 沪深港通持股（北向资金）
- `load_locked_shares(codes, ...)` — 限售解禁
- `load_factor_wide(factor_names, codes, ...)` — 260因子宽表
- `load_index_constituents(index_code, date)` — 指数成分股动态查询

---

## Phase C: ML/DL/RL 统一框架

**新增目录**:
```
ohmyquant/models/
├── __init__.py
├── base.py              # Model ABC + 注册器
├── feature_pipeline.py  # FeaturePipeline 特征工程
├── training.py          # TrainingPipeline 训练/推理分离
├── walk_forward.py      # WalkForwardRunner 滚动训练
├── ml/
│   ├── __init__.py
│   ├── lightgbm_model.py  # LightGBMModel
│   └── xgboost_model.py   # XGBoostModel
├── dl/
│   ├── __init__.py
│   ├── base_nn.py         # BaseNNModel (PyTorch)
│   ├── mlp_model.py       # MLP选股模型
│   └── lstm_model.py      # LSTM时序模型
└── rl/
    ├── __init__.py
    ├── base_rl.py         # BaseRLModel (stable-baselines3)
    └── portfolio_rl.py    # 组合管理RL agent
```

**核心接口**:
- `Model(ABC)`: `fit(X, y, groups, val_data)` → `predict(X)` → `save/load(path)`
- `FeaturePipeline`: 链式变换器（Rank/ZScore/Winsorize/IndustryNeutral/Lag）
- `TrainingPipeline`: 滚动训练 + 推理分离
- `WalkForwardRunner`: walk-forward 分割生成器

**集成点**:
- [plugin_system.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/plugin_system.py) — `PluginType` 新增 `MODEL`，新增 `register_model` 装饰器
- [ml_selector.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/ml_selector.py) — 重构为使用 FeaturePipeline + TrainingPipeline
- 新增 `ohmyquant/engine/selectors/model_selector.py` — 通用模型选股器
- [config_models.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/config_models.py) — `SelectionConfig` 新增 `model_name` 字段

**关键设计**: Model ABC 独立于选股器，可复用于信号生成、风险预测等场景。FeaturePipeline 与 Model 解耦。

---

## Phase D: ETF 与多资产支持

**新增文件**:
```
ohmyquant/strategy/strategies/etf/
├── __init__.py
├── v1/strategy.py    # ETF轮动策略（动量+ETFCostModel）
└── v2/strategy.py    # A股+ETF混合策略（N池架构）
```

**集成点**:
- DuckDBSource `_detect_asset_type`（第402-411行）已能自动识别 ETF 代码
- `load_daily_price` 已能从 `etf_daily_wide` 加载 ETF 行情
- BacktestEngine N池架构天然支持多资产（A股池+ETF池）
- [rebalancer.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/rebalancer.py) — 支持混合成本模型（按标的类型选择 stock_cn / etf_cn）

---

## Phase E: 策略优化与集成

**新增目录**:
```
ohmyquant/optimization/
├── __init__.py
├── signal.py          # 信号生成框架（Signal ABC + FactorSignal/CompositeSignal/ModelSignal）
├── walk_forward.py    # 策略级 walk-forward 优化
├── param_search.py    # Optuna 参数搜索
└── ensemble.py        # 多策略集成（equal_weight/perf_weight/ir_weight）
```

**关键接口**:
- `Signal(ABC).generate(data, idx, codes) → {code: signal_value}` — 解耦信号与选股
- `StrategyWalkForward.run(strategy_type, version, param_space) → WalkForwardReport`
- `ParamSearcher.search(strategy_type, version, param_space) → OptimizationReport` — Optuna 集成
- `StrategyEnsemble.add_strategy(type, version, weight).run() → EnsembleResult`

---

## 实施顺序

```
A (NAV Bug) → B (数据增强) → C (ML/DL/RL) → D (ETF) → E (优化集成)
```

A 最先修复（所有验证依赖正确回测），B 为 C 提供数据基础，C 为 E 提供模型基础，D 依赖 B 的 ETF 数据。

---

## 验证方案

1. **NAV Bug**: 回测起点 NAV=1.0，daily_returns 与 dates 对齐
2. **数据增强**: 每类新数据加载测试，因子宽表与 FactorLibrary 交叉验证
3. **ML框架**: LightGBMModel + FeaturePipeline 跑通 ycj 因子数据全流程
4. **DL框架**: MLP 模型训练/推理测试
5. **ETF策略**: 5-10只主流ETF跑通全流程，验证 ETFCostModel 生效
6. **混合策略**: A股池走 StockCostModel、ETF池走 ETFCostModel
7. **Walk-forward**: ycj v1 跑4个窗口验证 Sharpe 稳定性
8. **Optuna**: 搜索 top_n 和 target_vol 验证 Sharpe 提升
9. **Ensemble**: ycj v1 + etf v1 组合验证 Sharpe > 单策略
