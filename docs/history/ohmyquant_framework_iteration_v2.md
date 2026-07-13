# OhMyQuant 框架全面迭代计划 v2

## Summary

对 OhMyQuant 量化框架进行全面迭代，补齐数据兼容性、ML/DL/RL 统一框架、ETF 多资产支持、策略优化与集成四大能力缺口。目标是打造支持传统/ML/DL/RL 策略、覆盖 A股+ETF、可快速迭代验证的量化框架。

**实施顺序**: B（数据增强收尾）→ ycj 试运行修复 → C（ML/DL/RL）→ D（ETF）→ E（优化集成）

---

## Current State Analysis

### 已完成
- **Phase 1-10 基础框架**: 策略/回测/分析/可视化/跟踪/集成/CLI/配置/测试
- **Phase A NAV Bug**: 已修复（backtest.py 归一化回测起点 NAV=1.0）
- **Phase B 部分**: DuckDBSource 已扩展 22 视图 + 6 个新加载方法

### 关键缺口

| 模块 | 现状 | 缺口 |
|------|------|------|
| 数据层 | DuckDBSource 已扩展，但 base.py/CSVSource/LocalParquetSource 未同步 | DataSource ABC 缺 6 个抽象方法，DataCatalog 缺代理方法 |
| ycj 策略 | 默认 `data.source: csv`，股票池为空 | 需改用 duckdb + 指定股票池 |
| ML/DL/RL | 仅有 LightGBM LTR 选股器，特征硬编码 | 无 models/ 目录，无 Model ABC/FeaturePipeline |
| ETF | 有 ETFCostModel，但无 ETF 策略 | 无混合成本模型，无 ETF 策略模板 |
| 优化 | 无 | 无 optimization/ 目录，无 Walk-forward/Optuna/Ensemble |

### 数据资源（D:\Work\Project\download_a_share\data）
- 27 个 parquet 子目录：stock_daily_wide_partitioned、etf_daily_wide_partitioned、parquet/（含 25 类子数据）
- 覆盖：行情/估值/资金流/融资融券/行业/ST/财务报表(4类)/龙虎榜/北向资金/限售解禁/因子宽表(260)/ETF扩展(3类)/指数成分/概念等

---

## Phase B: 数据能力增强收尾

### B1. base.py — DataSource ABC 新增方法（带默认实现）

**文件**: `ohmyquant/data/base.py`

在 `DataSource` ABC 的 `get_all_etfs` 方法后（约第118行），新增 6 个方法。**不用 @abstractmethod**，而是提供默认实现返回空值，避免破坏 CSVSource/LocalParquetSource：

```python
def load_financial_statement(self, statement_type, codes, start_date=None, end_date=None) -> pl.DataFrame:
    """加载财务报表（income/balance/cash_flow/indicator）。默认实现返回空。"""
    return pl.DataFrame()

def load_billboard(self, codes=None, start_date=None, end_date=None) -> pl.DataFrame:
    """加载龙虎榜数据。默认实现返回空。"""
    return pl.DataFrame()

def load_hk_holdings(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
    """加载北向资金持股。默认实现返回空。"""
    return pl.DataFrame()

def load_locked_shares(self, codes=None, start_date=None, end_date=None) -> pl.DataFrame:
    """加载限售解禁。默认实现返回空。"""
    return pl.DataFrame()

def load_factor_wide(self, factor_names=None, codes=None, start_date=None, end_date=None) -> pl.DataFrame:
    """加载因子宽表。默认实现返回空。"""
    return pl.DataFrame()

def load_index_constituents(self, index_code, date=None) -> list[Code]:
    """加载指数成分股。默认实现返回空。"""
    return []
```

### B2. base.py — DataCatalog 新增代理方法

**文件**: `ohmyquant/data/base.py`

在 `DataCatalog.get_all_etfs` 方法后（约第330行），新增 6 个代理方法（调用 `self.source.load_xxx`）：

```python
def get_financial_statement(self, statement_type, codes, start_date=None, end_date=None) -> pl.DataFrame:
    return self.source.load_financial_statement(statement_type, codes, start_date, end_date)

def get_billboard(self, codes=None, start_date=None, end_date=None) -> pl.DataFrame:
    return self.source.load_billboard(codes, start_date, end_date)

def get_hk_holdings(self, codes, start_date=None, end_date=None) -> pl.DataFrame:
    return self.source.load_hk_holdings(codes, start_date, end_date)

def get_locked_shares(self, codes=None, start_date=None, end_date=None) -> pl.DataFrame:
    return self.source.load_locked_shares(codes, start_date, end_date)

def get_factor_wide(self, factor_names=None, codes=None, start_date=None, end_date=None) -> pl.DataFrame:
    return self.source.load_factor_wide(factor_names, codes, start_date, end_date)

def get_index_constituents(self, index_code, date=None) -> list[Code]:
    return self.source.load_index_constituents(index_code, date)
```

### B3. CSVSource / LocalParquetSource

**文件**: `ohmyquant/data/sources/csv_source.py`、`ohmyquant/data/sources/local_parquet_source.py`

**不需要修改**。由于 B1 使用默认实现（返回空），CSVSource 和 LocalParquetSource 自动继承空实现，不会破坏现有代码。若后续需要 LocalParquetSource 支持新数据，再单独实现。

### B4. 验证

- 运行 `python -c "from ohmyquant.data.sources.duckdb_source import DuckDBSource; s=DuckDBSource({'data_root':'D:/Work/Project/download_a_share/data'}); print(s.load_index_constituents('000300.SH')[:5])"` 验证成分股加载
- 验证 `DataCatalog` 代理方法可调用

---

## ycj 试运行修复

### Y1. 策略默认数据源改为 duckdb

**文件**:
- `ohmyquant/strategy/strategies/ycj/v1/strategy.py`（第72行）
- `ohmyquant/strategy/strategies/ycj/v2/strategy.py`（第85行）
- `ohmyquant/strategy/strategies/dh/v1/strategy.py`（第71行）
- `ohmyquant/strategy/strategies/ycj/v1/config.yaml`（第37行）

将 `"data": {"source": "csv"}` 改为 `"data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"}`

### Y2. 试运行脚本

创建 `scripts/run_ycj_smoke.py`：
- 用 `load_index_constituents('000300.SH')` 加载沪深300成分股作为股票池
- 通过 `config_overrides` 传入股票池和数据源配置
- 缩短回测区间（2023-01-01 → 2024-12-31）加快验证
- 打印关键指标：final_nav、sharpe、max_drawdown、调仓次数

### Y3. 试运行验证

执行脚本，记录暴露的问题（功能缺失/性能瓶颈/异常），在完成后汇总。

---

## Phase C: ML/DL/RL 统一框架

### C1. 插件系统扩展

**文件**: `ohmyquant/core/plugin_system.py`

- `PluginType` 枚举新增 `MODEL = "model"`（第41行后）
- 新增 `register_model` 装饰器（第269行后）
- `__all__` 新增 `register_model`

### C2. 配置扩展

**文件**: `ohmyquant/core/config_models.py`

`SelectionConfig` 新增字段（第56行后）：
```python
model_name: str = ""  # 模型插件名（如 lightgbm_ltr / mlp / lstm）
model: dict[str, Any] = Field(default_factory=dict)  # 模型超参
```

### C3. 新建 models/ 目录

```
ohmyquant/models/
├── __init__.py          # 导出核心类
├── base.py              # Model ABC + FeaturePipeline + TrainingPipeline
├── features.py          # 特征变换器（Rank/ZScore/Winsorize/IndustryNeutral/Lag）
├── walk_forward.py      # WalkForwardRunner 滚动训练分割
├── ml/
│   ├── __init__.py
│   ├── lightgbm_model.py  # LightGBMModel（迁移自 ml_selector）
│   └── xgboost_model.py   # XGBoostModel
├── dl/
│   ├── __init__.py
│   ├── base_nn.py         # BaseNNModel（PyTorch，try import）
│   ├── mlp_model.py       # MLP 选股模型
│   └── lstm_model.py      # LSTM 时序模型
└── rl/
    ├── __init__.py
    ├── base_rl.py         # BaseRLModel（stable-baselines3，try import）
    └── portfolio_rl.py    # 组合管理 RL agent
```

### C4. Model ABC 核心接口

**文件**: `ohmyquant/models/base.py`

```python
class Model(ABC):
    """模型抽象基类，独立于选股器，可复用于信号生成/风险预测"""
    def __init__(self, config: dict | None = None): ...
    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray | None = None,
            val_data: tuple | None = None) -> None: ...
    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def save(self, path: str) -> None: ...
    @abstractmethod
    def load(self, path: str) -> None: ...

class FeaturePipeline:
    """链式特征变换器"""
    def add_transform(self, name: str, **kwargs) -> "FeaturePipeline": ...
    def fit_transform(self, df: pl.DataFrame) -> np.ndarray: ...
    def transform(self, df: pl.DataFrame) -> np.ndarray: ...

class TrainingPipeline:
    """训练/推理分离管道"""
    def __init__(self, model: Model, feature_pipeline: FeaturePipeline): ...
    def train(self, factors, fwd_returns, stock_codes, current_idx) -> None: ...
    def predict(self, factors, stock_codes, current_idx) -> dict[str, float]: ...
```

**变换器**（`features.py`）:
- `RankTransform`: 截面排名归一化
- `ZScoreTransform`: 截面 z-score
- `WinsorizeTransform`: 缩尾（默认 1%/99%）
- `IndustryNeutralTransform`: 行业中性化
- `LagTransform`: 时滞处理

### C5. ML 模型实现

**文件**: `ohmyquant/models/ml/lightgbm_model.py`
- `@register_model("lightgbm_ltr")` LightGBMModel
- 迁移 `ml_selector.py` 的 `_train_ltr` 逻辑到 Model.fit
- 支持 LGBMRanker 和 LGBMRegressor 两种模式

**文件**: `ohmyquant/models/ml/xgboost_model.py`
- `@register_model("xgboost_ltr")` XGBoostModel
- try import xgboost，不可用时注册时警告

### C6. DL 模型实现（try import PyTorch）

**文件**: `ohmyquant/models/dl/base_nn.py`
- `BaseNNModel(Model)`: PyTorch 基类，封装训练循环/早停/设备管理
- try import torch，不可用时类定义但实例化报错

**文件**: `ohmyquant/models/dl/mlp_model.py`
- `@register_model("mlp")` MLPModel: 多层感知机选股

**文件**: `ohmyquant/models/dl/lstm_model.py`
- `@register_model("lstm")` LSTMModel: 时序特征提取

### C7. RL 模型实现（try import stable-baselines3）

**文件**: `ohmyquant/models/rl/base_rl.py`
- `BaseRLModel(Model)`: RL 基类，封装环境/训练/推理
- try import stable_baselines3，不可用时类定义但实例化报错

**文件**: `ohmyquant/models/rl/portfolio_rl.py`
- `@register_model("ppo_portfolio")` PortfolioRLModel: PPO 组合管理

### C8. 重构 ml_selector + 新增 model_selector

**文件**: `ohmyquant/engine/selectors/ml_selector.py`
- 保留现有实现作为兼容，但内部委托给 `TrainingPipeline + LightGBMModel`
- 提取 `_build_cross_section_features` 到 FeaturePipeline

**文件**: `ohmyquant/engine/selectors/model_selector.py`（新增）
- `@register_selector("model")` ModelSelector
- 通用模型选股器，通过 `selection.model_name` 选择模型插件
- 支持 walk-forward 滚动训练

**文件**: `ohmyquant/engine/selectors/__init__.py`
- 注册 model_selector

### C9. WalkForwardRunner

**文件**: `ohmyquant/models/walk_forward.py`
```python
class WalkForwardRunner:
    """滚动训练分割生成器"""
    def __init__(self, train_window: int = 252, test_window: int = 63,
                 step: int = 63, retrain_freq: int = 21): ...
    def splits(self, dates: list[str]) -> Iterator[tuple[list[str], list[str]]]: ...
    def run(self, pipeline: TrainingPipeline, data, dates) -> dict: ...
```

---

## Phase D: ETF 与多资产支持

### D1. 混合成本模型

**文件**: `ohmyquant/execution/cost_model.py`

新增 `MixedCostModel`：
```python
@register_cost_model("mixed_cn")
class MixedCostModel(BaseCostModel):
    """混合成本模型：按标的类型自动选择 stock_cn / etf_cn"""
    def __init__(self, config=None):
        self.stock_model = StockCostModel(config)
        self.etf_model = ETFCostModel(config)
    def _is_etf(self, code: str) -> bool: ...
    def buy_cost(self, weight, code=None) -> float: ...
    def sell_cost(self, weight, hold_days=0, code=None) -> float: ...
    def estimate(self, old_weights, new_weights, hold_days_map=None) -> float: ...
```

修改 `BaseCostModel.buy_cost/sell_cost` 签名，新增可选 `code` 参数（默认 None 保持兼容）。

### D2. Rebalancer 支持混合成本

**文件**: `ohmyquant/execution/rebalancer.py`

`CostBenefitRebalancer` 和 `SimpleRebalancer` 的 `decide` 方法中，调用 `cost_model.estimate` 时传入 codes（混合模型按 code 选择成本）。修改 `estimate` 调用传入 `old_weights`/`new_weights` 的 keys 作为 codes。

### D3. ETF 策略模板

**文件**: `ohmyquant/strategy/strategies/etf/v1/strategy.py`（新增）
- `@register_strategy("etf", "v1")` ETFRotationV1
- ETF 动量轮动策略：5-10 只主流 ETF，按 20日动量排名选 Top-3
- 使用 `etf_cn` 成本模型
- 股票池示例: 510300.SH(沪深300ETF) / 510500.SH(中证500) / 159915.SZ(创业板) / 588000.SH(科创50) / 510050.SH(50ETF) / 512100.SH(中证1000) / 515790.SH(光伏) / 512480.SH(半导体)

**文件**: `ohmyquant/strategy/strategies/etf/v2/strategy.py`（新增）
- `@register_strategy("etf", "v2")` ETFMixedV2
- A股 + ETF 混合策略：N池架构（stock_pool + etf_pool）
- 使用 `mixed_cn` 成本模型

**文件**: `ohmyquant/strategy/strategies/etf/__init__.py`、`v1/__init__.py`、`v2/__init__.py`（新增空文件）

### D4. 策略注册

**文件**: `ohmyquant/strategy/strategies/__init__.py`
- 导入 etf 策略模块以触发注册

---

## Phase E: 策略优化与集成

### E1. 新建 optimization/ 目录

```
ohmyquant/optimization/
├── __init__.py
├── signal.py          # 信号生成框架
├── walk_forward.py    # 策略级 walk-forward
├── param_search.py    # Optuna 参数搜索
└── ensemble.py        # 多策略集成
```

### E2. 信号框架

**文件**: `ohmyquant/optimization/signal.py`
```python
class Signal(ABC):
    """信号抽象基类，解耦信号生成与选股"""
    @abstractmethod
    def generate(self, data, idx, codes) -> dict[str, float]: ...

class FactorSignal(Signal):
    """单因子信号"""
class CompositeSignal(Signal):
    """多因子加权信号"""
class ModelSignal(Signal):
    """模型预测信号"""
```

### E3. Walk-forward 优化

**文件**: `ohmyquant/optimization/walk_forward.py`
```python
class StrategyWalkForward:
    """策略级 walk-forward 优化"""
    def __init__(self, train_window: str, test_window: str, step: str): ...
    def run(self, strategy_type: str, version: str,
            param_space: dict) -> "WalkForwardReport": ...
```

### E4. Optuna 参数搜索

**文件**: `ohmyquant/optimization/param_search.py`
```python
class ParamSearcher:
    """Optuna 参数搜索"""
    def __init__(self, n_trials: int = 50, metric: str = "sharpe"): ...
    def search(self, strategy_type: str, version: str,
               param_space: dict) -> "OptimizationReport": ...
```
try import optuna，不可用时警告。

### E5. 多策略集成

**文件**: `ohmyquant/optimization/ensemble.py`
```python
class StrategyEnsemble:
    """多策略集成"""
    def add_strategy(self, strategy_type: str, version: str, weight: float): ...
    def run(self) -> "EnsembleResult": ...
```
支持 equal_weight / perf_weight / ir_weight 三种加权方式。

---

## Assumptions & Decisions

1. **数据源默认值**: 策略默认 `data.source` 从 `csv` 改为 `duckdb`，因为 download_a_share 是主要数据源
2. **ycj 试运行股票池**: 用沪深300成分股（`load_index_constituents('000300.SH')`），约300只，足够强因子筛选
3. **DL/RL 依赖**: 用 try import 模式，不强制安装 PyTorch/stable-baselines3。框架提供抽象和模板，用户按需安装
4. **CSVSource/LocalParquetSource**: 不新增6个方法的实现，继承 DataSource ABC 的默认空实现。DuckDBSource 是主要数据源
5. **混合成本模型**: 新增 `mixed_cn` 成本模型，不修改现有 `stock_cn`/`etf_cn`。BaseCostModel 的 buy_cost/sell_cost 新增可选 code 参数保持向后兼容
6. **ml_selector 兼容**: 保留现有 MLSelector 注册名 `ml`，新增 `model` 选股器作为通用入口
7. **Optuna 可选**: try import optuna，不可用时 ParamSearcher 降级为网格搜索

---

## Verification Steps

### Phase B 验证
1. `DuckDBSource.load_index_constituents('000300.SH')` 返回约300只成分股
2. `DuckDBSource.load_financial_statement('income', ['000001.SZ'])` 返回非空 DataFrame
3. `DataCatalog` 6 个新代理方法可调用

### ycj 试运行验证
4. ycj v1 全流程跑通：数据加载 → 因子计算 → IC 分析 → 选股 → 回测 → 绩效指标
5. NAV[0] = 1.0，final_nav 合理（累计收益与净值一致）
6. 记录暴露的问题清单

### Phase C 验证
7. `PluginType.MODEL` 存在，`register_model` 可用
8. `LightGBMModel` + `FeaturePipeline` 跑通 ycj 因子数据训练/推理
9. `MLPModel`（若 PyTorch 可用）训练/推理测试
10. `ModelSelector`（selection.method=model）跑通全流程

### Phase D 验证
11. ETF v1 轮动策略跑通，`ETFCostModel` 生效
12. ETF v2 混合策略跑通，A股池走 `StockCostModel`、ETF 池走 `ETFCostModel`
13. `MixedCostModel.estimate` 按标的类型分别计算成本

### Phase E 验证
14. `StrategyWalkForward.run('ycj', 'v1', ...)` 跑通 4 个窗口
15. `ParamSearcher.search` 搜索 top_n/target_vol 验证 Sharpe 变化
16. `StrategyEnsemble` 组合 ycj v1 + etf v1，验证 Sharpe > 单策略

### 全量测试
17. `pytest tests/` 全部通过
