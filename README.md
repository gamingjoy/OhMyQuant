# OhMyQuant

> **一站式量化策略开发框架** — 从数据到策略，从回测到实盘，让量化投资更简单

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 30 passed](https://img.shields.io/badge/tests-30%20passed-brightgreen.svg)](#测试)

OhMyQuant 是一个模块化、可扩展的量化策略开发框架，支持 A股和 ETF 等金融产品的策略开发、回测与分析。框架兼容传统主观策略、机器学习（ML）、深度学习（DL）和强化学习（RL）策略，提供从数据接入到策略迭代的完整工具链。

---

## 目录

- [核心特性](#核心特性)
- [架构总览](#架构总览)
- [安装](#安装)
- [快速开始](#快速开始)
- [策略开发指南](#策略开发指南)
- [因子开发指南](#因子开发指南)
- [ML/DL/RL 模型接入](#mldlrl-模型接入)
- [配置系统](#配置系统)
- [CLI 命令行工具](#cli-命令行工具)
- [测试](#测试)
- [项目结构](#项目结构)
- [数据兼容性](#数据兼容性)
- [FAQ](#faq)

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **多策略统一** | 传统主观策略、ML（LightGBM/XGBoost）、DL（LSTM/MLP）、RL（PPO）在同一框架下开发与回测 |
| **插件化架构** | 因子、选股器、风控、分配器、调仓器、成本模型、数据源、模型全部可插拔注册 |
| **N 池回测引擎** | 支持多股票池并行回测，池间动态分配，向量化解算 |
| **31 个内置因子** | 动量、反转、技术、估值、波动率、量价、基本面 7 大类 |
| **Walk-Forward 训练** | 滚动窗口训练 + 重训练频率控制，杜绝前视偏差 |
| **DuckDB 加速** | 通过 DuckDB 视图查询 Parquet，谓词下推，零拷贝 Arrow→polars |
| **完整分析链** | 绩效指标、统计显著性检验、多策略对比、归因分析、交互式仪表盘 |
| **A股本土化** | T+1 交易成本模型、涨跌停限制、ST 过滤、行业/概念分类、龙虎榜、北向资金 |

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI (omq)                                │
│  run · backtest · analyze · list · init · config               │
├─────────────────────────────────────────────────────────────────┤
│                     Strategy Layer                              │
│  Registry · Runner · VersionManager                            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ ycj v1  │ │ ycj v2  │ │ dh v1   │ │ etf v1  │ │ etf v2  │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│  ┌─────────┐ ┌─────────┐                                        │
│  │ dl v1   │ │ rl v1   │                                        │
│  └─────────┘ └─────────┘                                        │
├─────────────────────────────────────────────────────────────────┤
│                    Backtest Engine                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Selector │ │  Risk    │ │Allocator │ │Portfolio │          │
│  │ 7 types  │ │ Manager  │ │  HRP/EW  │ │ Optimizer│          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────────────────────────────────────────┐              │
│  │           Rebalancer + CostModel             │              │
│  └──────────────────────────────────────────────┘              │
├───────────────────┬───────────────────┬───────────────────────┤
│   Factor Library  │   Models (ML/DL/RL)  │  Optimization     │
│  31 factors, 7 cat│  LightGBM/LSTM/PPO   │  WalkForward/     │
│  IC/ICIR analysis │  FeaturePipeline     │  ParamSearch/     │
│                   │  TrainingPipeline    │  Ensemble         │
├───────────────────┴───────────────────┴───────────────────────┤
│                      Data Layer                                 │
│  DataCatalog → DataSource (DuckDB / CSV / Parquet)             │
│  26 views: 行情·估值·资金流·融资融券·财务·龙虎榜·北向·限售     │
├─────────────────────────────────────────────────────────────────┤
│  Analysis │ Visualization │ Tracking │ Integration │ Config    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 安装

### 前置条件

- Python 3.10+
- 操作系统: Windows / Linux / macOS

### 核心依赖安装

```bash
# 核心依赖（必需）
pip install polars duckdb pydantic loguru pyyaml

# 可选依赖（按需安装）
pip install lightgbm          # ML 策略
pip install torch             # DL 策略（LSTM/MLP）
pip install stable-baselines3 gymnasium  # RL 策略（PPO）
pip install plotly            # 可视化
pip install scipy             # 统计检验
```

### 框架安装

```bash
git clone <repo_url>
cd OhMyQuant
pip install -e .  # 开发模式安装（如有 setup.py）
# 或直接设置 PYTHONPATH
export PYTHONPATH=/path/to/OhMyQuant
```

### 数据准备

框架兼容 [download_a_share](https://github.com/) 数据目录结构：

```
data/
├── stock_daily_wide_partitioned/year=YYYY/data.parquet
├── etf_daily_wide_partitioned/year=YYYY/data.parquet
├── parquet/
│   ├── trade_calendar/
│   ├── stock_valuation/
│   ├── stock_money_flow/
│   ├── stock_margin_trading/
│   ├── stock_income/  stock_balance/  stock_cash_flow/  stock_indicator/
│   ├── stock_billboard/  stock_hk_hold/  stock_locked_shares/
│   ├── index_daily_price/  index_constituents/
│   └── ...
```

---

## 快速开始

### 3 行代码运行回测

```python
from ohmyquant.strategy.runner import StrategyRunner

# 运行 ycj v1 策略回测
result = StrategyRunner.run_strategy("ycj", "v1")

# 查看结果
bt = result.backtest_result
print(f"最终净值: {bt.final_nav:.4f}")
print(f"回测天数: {bt.n_days}")
```

### 使用 CLI

```bash
# 运行策略
python -m ohmyquant.cli run ycj v1

# 列出所有策略
python -m ohmyquant.cli list strategies

# 列出所有因子
python -m ohmyquant.cli list factors
```

### 运行烟雾测试

```bash
# 设置 PYTHONPATH
export PYTHONPATH=.

# 运行各类烟雾测试
python scripts/run_ycj_smoke.py      # YCJ 策略
python scripts/run_etf_smoke.py      # ETF 轮动
python scripts/run_ml_smoke.py       # ML (LightGBM)
python scripts/run_dl_smoke.py       # DL (LSTM)
python scripts/run_rl_smoke.py       # RL (PPO)
python scripts/run_optimization_smoke.py  # 优化模块
```

---

## 策略开发指南

### 策略类型总览

| 策略 | 版本 | 选股方法 | 适用场景 |
|------|------|----------|----------|
| `ycj` | v1 | ICIR | 量化选股（蓝筹池） |
| `ycj` | v2 | Hybrid (ICIR+ML) | 量化选股（高级） |
| `dh` | v1 | ICIR | 主观策略量化版 |
| `etf` | v1 | ICIR | ETF 动量轮动 |
| `etf` | v2 | Hybrid + HRP | ETF 混合策略 |
| `dl` | v1 | Model (LSTM) | 深度学习选股 |
| `rl` | v1 | RL (PPO) | 强化学习组合管理 |

### 创建新策略

1. **创建目录结构**

```
ohmyquant/strategy/strategies/<type>/<version>/
├── __init__.py
├── strategy.py
└── config.yaml
```

2. **实现策略类**

```python
# ohmyquant/strategy/strategies/mystrategy/v1/strategy.py
from ohmyquant.engine.base import BacktestResult
from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

@register_strategy("mystrategy", "v1")
class MyStrategyV1(BaseStrategy):
    """我的策略 v1"""

    def run(self) -> BacktestResult:
        from ...strategy.runner import StrategyRunner
        runner = StrategyRunner(self.config)
        return runner.run().backtest_result

    def get_latest_positions(self) -> dict[str, float]:
        return {}

    @classmethod
    def from_version(cls, strategy_type, version, config=None):
        if strategy_type != "mystrategy" or version != "v1":
            raise ValueError(f"不支持: {strategy_type} {version}")

        base_config = {
            "strategy_type": "mystrategy",
            "strategy_version": "v1",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2010-01-01",
            },
            "selection": {"method": "icir", "top_n": 20, "max_stock_weight": 0.05},
            "risk": {"target_vol": 0.20},
            "allocation": {"method": "equal"},
            "rebalance": {"frequency": "monthly", "method": "cost_benefit"},
            "factors": ["mom_1m", "mom_3m", "vol_20d"],
            "pools": {"main": ["600519.SH", "601318.SH", "000858.SZ"]},
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }
        if config:
            base_config.update(config)
        return cls(base_config)
```

3. **注册策略**

在 `ohmyquant/strategy/strategies/__init__.py` 中添加：

```python
try:
    from .mystrategy.v1.strategy import MyStrategyV1  # noqa: F401
except ImportError:
    pass
```

4. **创建配置文件** (config.yaml)

```yaml
strategy_type: mystrategy
strategy_version: v1
backtest:
  start_date: "2015-01-01"
  end_date: "2024-12-31"
selection:
  method: icir
  top_n: 20
factors: [mom_1m, mom_3m, vol_20d]
pools:
  main: ["600519.SH", "601318.SH"]
data:
  source: duckdb
  data_root: "D:/Work/Project/download_a_share/data"
```

### 7 种选股器

| 选股器 | method | 说明 | 适用场景 |
|--------|--------|------|----------|
| ICIRSelector | `icir` | 按信息系数/信息比率筛选强因子 | 通用选股 |
| HybridSelector | `hybrid` | ICIR 初筛 + ML 重排 | 高级选股 |
| AdaptiveICIRSelector | `adaptive` | 自适应 ICIR | 市场状态切换 |
| MomentumSelector | `momentum` | 不依赖 IC 的动量排名 | ETF 小池 |
| MLSelector | `ml` | 直接调用 ML 模型 | 机器学习 |
| ModelSelector | `model` | 通用模型选股（ML/DL） | ML/DL 策略 |
| RLSelector | `rl` | RL 直接输出权重 | RL 策略 |

---

## 因子开发指南

### 内置因子（31 个，7 大类）

| 类别 | 因子 | 数量 |
|------|------|------|
| 动量 (momentum) | mom_1m, mom_3m, mom_6m, mom_12m, mom_skip_1m | 5 |
| 反转 (reversal) | rev_5d, rev_10d, rev_20d | 3 |
| 技术 (technical) | rsi_14, ma_5_20_cross, bias_20, willr_14 | 4 |
| 估值 (valuation) | pe_ttm, pb_ratio, ps_ratio, market_cap | 4 |
| 波动率 (volatility) | vol_20d, vol_60d, vol_120d, amihud_illiq | 4 |
| 量价 (volume_price) | turnover_20d, volume_ratio, amount_20d, price_volume_corr, obv_slope | 5 |
| 基本面 (fundamental) | ep_ratio, bp_ratio, sp_ratio, turnover_ratio, log_market_cap, dividend_yield | 6 |

### 开发自定义因子

```python
# ohmyquant/factors/builtin/my_factor.py
import polars as pl
from ..base import Factor, register_factor

@register_factor("my_factor", category="custom")
class MyFactor(Factor):
    """自定义因子说明"""

    name = "my_factor"
    category = "custom"
    description = "我的自定义因子"
    direction = 1   # 1=正向（值大→收益高），-1=反向
    required_fields = ["close", "volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        volume = data["volume"]
        date_col = close["date"]
        close_num = close.drop("date")
        vol_num = volume.drop("date")

        # 计算因子值（返回 date × code 宽表）
        result = (close_num * vol_num).select(
            [pl.col(c).rolling_mean(window_size=20).alias(c) for c in close_num.columns]
        )
        return result.insert_column(0, date_col)
```

在 `ohmyquant/factors/builtin/__init__.py` 中注册：

```python
from . import my_factor
```

### 因子分析

```python
from ohmyquant.factors.analysis import FactorAnalyzer
from ohmyquant.factors.library import get_factor_library

lib = get_factor_library()
factor = lib.create("mom_1m")
factor_values = factor.compute(data)

# 计算 IC
ic_df = FactorAnalyzer.compute_ic(factor_values, forward_returns)
print(f"IC 均值: {ic_df['ic'].mean()}")
print(f"ICIR: {ic_df['ic'].mean() / ic_df['ic'].std()}")
```

---

## ML/DL/RL 模型接入

### 模型总览

| 类型 | 模型 | 注册名 | 依赖 | 选股器 |
|------|------|--------|------|--------|
| ML | LightGBM LTR/Regressor | `lightgbm_ltr` | lightgbm | model |
| ML | XGBoost | `xgboost` | xgboost | model |
| DL | LSTM | `lstm` | torch | model |
| DL | MLP | `mlp` | torch | model |
| RL | PPO Portfolio | `ppo_portfolio` | stable-baselines3 | rl |

### ML 策略示例（LightGBM）

```yaml
selection:
  method: model
  model_name: lightgbm_ltr
  model:
    n_estimators: 150
    max_depth: 3
  ml:
    train_window: 252
    target_horizon: 20
    retrain_freq: 21
  features:
    transforms: [rank, zscore]
  top_n: 50
  max_stock_weight: 0.02
```

### DL 策略示例（LSTM）

```yaml
selection:
  method: model
  model_name: lstm
  model:
    hidden_dim: 64
    num_layers: 2
    epochs: 30
    batch_size: 256
    device: auto       # auto/cpu/cuda
  ml:
    train_window: 252
    retrain_freq: 21
  features:
    transforms: [rank, zscore]
```

### RL 策略示例（PPO）

```yaml
selection:
  method: rl
  model_name: ppo_portfolio
  model:
    total_timesteps: 10000
    transaction_cost: 0.001
  ml:
    train_window: 252
    retrain_freq: 63    # 季度重训练
```

### 特征管线

```python
from ohmyquant.models import FeaturePipeline

pipeline = FeaturePipeline()
pipeline.add_transform("rank")           # 截面排名
pipeline.add_transform("zscore")         # 标准化
pipeline.add_transform("winsorize", lower=0.01, upper=0.99)  # 去极值
pipeline.add_transform("industry_neutral")  # 行业中性化
pipeline.add_transform("lag", periods=1)    # 滞后

X = pipeline.fit_transform(df)
```

### Walk-Forward 训练

框架内置 walk-forward 训练管道，自动处理：
- 滚动训练窗口（`train_window`）
- 重训练频率（`retrain_freq`）
- 前向收益标签计算（`target_horizon`）
- 标签离散化（LTR 5-bin 分级）
- 验证集自动分割

---

## 配置系统

### 配置层级

```
config/default_config.py    → 全局默认配置
strategy/.../config.yaml    → 策略版本配置
运行时 config_overrides      → 动态覆盖
```

### 完整配置示例

```yaml
# 策略元信息
strategy_type: ycj
strategy_version: v2
strategy_name: "YCJ 量化策略 v2"

# 回测配置
backtest:
  start_date: "2015-01-01"
  end_date: "2024-12-31"
  data_start_date: "2010-01-01"   # 因子计算需要更早的数据
  transaction_cost: 0.001
  train_end: "2024-12-31"         # IC 分析的训练集截止日

# 选股配置
selection:
  method: hybrid          # icir/hybrid/adaptive/momentum/ml/model/rl
  top_n: 100              # 选股数量
  max_stock_weight: 0.015 # 个股权重上限
  min_ic: 0.02            # 最小 IC 阈值
  min_ic_ir: 0.1          # 最小 ICIR 阈值

# 风控配置
risk:
  target_vol: 0.20        # 目标年化波动率
  vol_trend_mode: managed_vol  # managed_vol/fixed

# 分配配置
allocation:
  method: hrp             # hrp/equal/risk_parity/min_variance
  lookback: 60            # 协方差回看窗口

# 组合配置
portfolio:
  max_stock_weight: 0.025 # 个股权重上限（覆盖 selection）

# 调仓配置
rebalance:
  frequency: monthly      # daily/weekly/monthly/quarterly
  method: cost_benefit    # none/cost_benefit/threshold
  cost_benefit_threshold: 0.001
  weekday: 0              # 周一=0
  cost_model:
    name: stock_cn        # stock_cn/etf_cn/mixed_cn

# 因子列表
factors:
  - mom_1m
  - mom_3m
  - vol_20d

# 股票池
pools:
  main:
    - "600519.SH"
    - "601318.SH"

# 数据源
data:
  source: duckdb
  data_root: "D:/Work/Project/download_a_share/data"
```

---

## CLI 命令行工具

```bash
# 运行策略
omq run ycj v1
omq run dl v1 --config custom.yaml
omq run etf v1 --output ./results

# 执行回测（指定日期）
omq backtest --strategy ycj --version v1 --start 2020-01-01 --end 2024-12-31

# 分析结果
omq analyze --results results.json --metrics
omq analyze --results r1.json --compare r2.json --report report.html

# 列出可用资源
omq list strategies
omq list factors
omq list data_sources

# 初始化项目
omq init my_strategy --type strategy

# 配置管理
omq config show
omq config set --key data.source --value duckdb
omq config reset
```

---

## 测试

### 运行测试套件

```bash
# 全部测试
python -m pytest tests/ -v

# 指定模块
python -m pytest tests/test_backtest.py -v
python -m pytest tests/test_strategy.py -v

# 带覆盖率
python -m pytest tests/ --cov=ohmyquant --cov-report=html
```

### 测试覆盖

| 测试文件 | 覆盖模块 | 测试数 |
|----------|----------|--------|
| test_core.py | 插件系统、配置加载 | 8 |
| test_strategy.py | 策略注册、版本管理 | 5 |
| test_backtest.py | 成本模型、执行器、引擎 | 6 |
| test_analysis.py | 绩效指标、对比、显著性 | 11 |

### 烟雾测试

烟雾测试验证端到端全流程，使用真实数据：

```bash
# 设置 PYTHONPATH
export PYTHONPATH=.

# 各类策略烟雾测试
python scripts/run_ycj_smoke.py          # YCJ 策略 (~15s)
python scripts/run_etf_smoke.py          # ETF 轮动 (~10s)
python scripts/run_ml_smoke.py           # ML LightGBM (~20s)
python scripts/run_dl_smoke.py           # DL LSTM (~40s)
python scripts/run_rl_smoke.py           # RL PPO (~40s)
python scripts/run_optimization_smoke.py # 优化模块 (~15s)
```

---

## 项目结构

```
OhMyQuant/
├── ohmyquant/                    # 框架核心包
│   ├── core/                     # 核心基础设施
│   │   ├── config_models.py      #   Pydantic 配置模型
│   │   ├── plugin_system.py      #   插件注册系统
│   │   ├── types.py              #   类型定义
│   │   ├── cache.py              #   LRU 缓存
│   │   └── logging.py            #   日志配置
│   ├── data/                     # 数据层
│   │   ├── base.py               #   DataSource ABC + DataCatalog
│   │   └── sources/
│   │       └── duckdb_source.py  #   DuckDB 数据源（26 视图）
│   ├── factors/                  # 因子平台
│   │   ├── base.py               #   Factor ABC + Registry
│   │   ├── library.py            #   FactorLibrary
│   │   ├── analysis.py           #   IC/ICIR 分析
│   │   └── builtin/              #   31 个内置因子（7 类）
│   ├── engine/                   # 回测引擎
│   │   ├── backtest.py           #   N 池向量化回测引擎
│   │   ├── base.py               #   BacktestResult
│   │   ├── selector.py           #   BaseSelector
│   │   ├── selectors/            #   7 种选股器
│   │   ├── allocators.py         #   分配器（HRP/EW/RP）
│   │   ├── risk_managers.py      #   风控管理器
│   │   └── portfolio.py          #   组合优化器
│   ├── models/                   # ML/DL/RL 模型
│   │   ├── base.py               #   Model ABC + TrainingPipeline
│   │   ├── features.py           #   5 种特征变换器
│   │   ├── ml/                   #   LightGBM + XGBoost
│   │   ├── dl/                   #   LSTM + MLP (PyTorch)
│   │   └── rl/                   #   PPO Portfolio (stable-baselines3)
│   ├── strategy/                 # 策略管理
│   │   ├── base.py               #   BaseStrategy
│   │   ├── registry.py           #   StrategyRegistry
│   │   ├── runner.py             #   StrategyRunner
│   │   └── strategies/           #   7 个策略版本
│   ├── execution/                # 执行系统
│   │   ├── cost_model.py         #   交易成本模型
│   │   ├── rebalancer.py         #   调仓器
│   │   └── scheduler.py          #   调仓调度器
│   ├── optimization/             # 策略优化
│   │   ├── signal.py             #   信号生成
│   │   ├── walk_forward.py       #   Walk-Forward 验证
│   │   ├── param_search.py       #   参数搜索
│   │   └── ensemble.py           #   策略集成
│   ├── analysis/                 # 分析模块
│   │   ├── metrics.py            #   绩效指标
│   │   ├── compare.py            #   多策略对比
│   │   ├── significance.py       #   统计显著性
│   │   ├── attribution.py        #   归因分析
│   │   └── report.py             #   报告生成
│   ├── visualization/            # 可视化
│   │   ├── plots.py              #   Plotly 图表
│   │   ├── dashboard.py          #   交互式仪表盘
│   │   └── themes.py             #   主题配置
│   ├── tracking/                 # 实验跟踪
│   ├── integration/              # 外部集成
│   ├── cli/                      # 命令行工具
│   └── config/                   # 默认配置
├── scripts/                      # 烟雾测试脚本
├── tests/                        # 单元测试
└── README.md                     # 本文档
```

---

## 数据兼容性

框架与 `download_a_share` 数据目录完全兼容，支持以下数据：

### 数据覆盖（26 个视图）

| 数据类别 | 视图名 | 说明 |
|----------|--------|------|
| 行情 | stock_daily_wide | A股日线（OHLCV+复权） |
| 行情 | etf_daily_wide | ETF 日线 |
| 估值 | stock_valuation | PE/PB/PS/换手率/市值 |
| 资金流 | stock_money_flow | 大单/中单/小单资金流 |
| 融资融券 | stock_margin_trading | 融资余额/融券余额 |
| 行业 | stock_industry / stock_industry_daily | 行业分类 |
| ST 状态 | stock_st_status | ST/*ST 标记 |
| 证券信息 | security_info | 上市状态/类型 |
| 指数 | index_daily_price | 指数行情 |
| 指数成分 | index_constituents | 沪深300/中证500等成分股 |
| 财务报表 | stock_income/balance/cash_flow/indicator | 四大报表 |
| 龙虎榜 | stock_billboard | 龙虎榜数据 |
| 北向资金 | stock_hk_hold | 沪深港通持股 |
| 限售解禁 | stock_locked_shares | 解禁明细 |
| ETF 扩展 | etf_net_value/share/margin/portfolio_stock | ETF 净值/份额/持仓 |
| 概念 | stock_concept | 概念/主题分类 |
| 因子 | factors / factors_wide | 预计算因子库 |
| 日历 | trade_calendar | 交易日历 |

### 数据使用示例

```python
from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.data.base import DataCatalog

source = DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"})
catalog = DataCatalog(source)

# 获取行情
ohlcv = catalog.get_ohlcv(["600519.SH"], "2020-01-01", "2024-12-31")

# 获取估值
valuation = catalog.get_valuation(["600519.SH"], "2020-01-01", "2024-12-31")

# 获取指数成分股
hs300 = catalog.get_index_constituents("000300.SH")

# 获取财务报表
income = catalog.get_financial_statement("income", ["600519.SH"], "2020-01-01", "2024-12-31")
```

---

## FAQ

### Q: 策略运行报 "未指定股票池 pools"？

A: 在 config.yaml 或 from_version 中添加 `pools` 配置。StrategyRegistry.create 会绕过 from_version，所以 config.yaml 中必须有 pools。

### Q: ETF 策略 ICIR 选不出股票？

A: ETF 池通常只有 8-12 只，IC/ICIR 统计在小样本下不稳定。使用 `method: momentum` 选股器替代，它不依赖 IC 筛选。

### Q: ML 策略 0 个调仓日？

A: 检查 ModelSelector 是否收到了 `fwd_returns`。BacktestEngine 会自动传递，但如果自定义选股流程需手动传入。

### Q: DL/RL 模型训练太慢？

A: 减小 `epochs`/`total_timesteps`，使用 `device: cpu`（小模型 CPU 可能更快），增大 `retrain_freq` 减少重训练次数。

### Q: 如何添加新的数据源？

A: 实现 `DataSource` ABC 的所有抽象方法，用 `@register_data_source("my_source")` 注册，然后在 config 中指定 `source: my_source`。

---

## License

MIT
