# OhMyQuant

> **一站式量化策略开发框架** — 从数据到策略，从回测到实盘，让量化投资更简单

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 187 passed](https://img.shields.io/badge/tests-187%20passed-brightgreen.svg)](#测试)

OhMyQuant 是一个模块化、可扩展的量化策略开发框架，支持 A股和 ETF 等金融产品的策略开发、回测与分析。支持行业轮动、专家集成等多种量化策略，支持插件化扩展，提供从数据接入到策略迭代的完整工具链。

---

## 目录

- [核心特性](#核心特性)
- [架构总览](#架构总览)
- [安装](#安装)
- [快速开始](#快速开始)
- [策略开发指南](#策略开发指南)
- [因子开发指南](#因子开发指南)
- [配置系统](#配置系统)
- [CLI 命令行工具](#cli-命令行工具)
- [测试](#测试)
- [项目结构](#项目结构)
- [数据兼容性](#数据兼容性)
- [FAQ](#faq)
- [Changelog](#changelog)

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **多策略统一** | 多策略在同一框架下开发与回测，支持插件化扩展 |
| **插件化架构** | 因子、选股器、风控、分配器、调仓器、成本模型、数据源全部可插拔注册 |
| **N 池回测引擎** | 支持多股票池并行回测，池间动态分配，向量化解算 |
| **31 个内置因子** | 动量、反转、技术、估值、波动率、量价、基本面 7 大类 |
| **Walk-Forward 验证** | 滚动窗口切分回测区间，评估策略跨周期稳定性，杜绝前视偏差 |
| **DuckDB 加速** | 通过 DuckDB 视图查询 Parquet，谓词下推，零拷贝 Arrow→polars |
| **完整分析链** | 绩效指标、统计显著性检验、多策略对比、归因分析、交互式仪表盘 |
| **A股本土化** | T+1 交易成本模型、涨跌停限制、ST 过滤、行业/概念分类、龙虎榜、北向资金 |

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI (omq)                                │
│  run · backtest · analyze · list · init · config               │
│  compare · optimize · signal · ensemble                        │
├─────────────────────────────────────────────────────────────────┤
│                     Strategy Layer                              │
│  Registry · Runner · VersionManager                            │
│  ┌────────────────────────┐ ┌──────────────────────┐          │
│  │ industry_rotation v66  │ │ expertForest_v1      │          │
│  └────────────────────────┘ └──────────────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│                    Backtest Engine                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Selector │ │  Risk    │ │Allocator │ │Portfolio │          │
│  │ 1 type   │ │ Manager  │ │  EW/HRP  │ │ Optimizer│          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────────────────────────────────────────┐              │
│  │           Rebalancer + CostModel             │              │
│  └──────────────────────────────────────────────┘              │
├───────────────────────────────────┬───────────────────────┤
│         Factor Library            │     Optimization      │
│      31 factors, 7 categories     │   WalkForward/        │
│        IC/ICIR analysis           │   ParamSearch/Ensemble│
├───────────────────────────────────┴───────────────────────┤
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
# 安装框架（开发模式，包含 dev 依赖）
pip install -e ".[dev]"

# 或仅安装核心依赖
pip install -e .

# 可选依赖（按需安装）
pip install -e ".[viz,stats]"   # 可视化 + 统计检验
pip install -e ".[all]"          # 全部可选依赖
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

# 运行 industry_rotation v66 策略回测
result = StrategyRunner.run_strategy("industry_rotation", "v66")

# 查看结果
bt = result.backtest_result
print(f"最终净值: {bt.final_nav:.4f}")
print(f"回测天数: {bt.n_days}")
```

### 使用 CLI

```bash
# 运行策略
python -m ohmyquant.cli run industry_rotation v66

# 列出所有策略
python -m ohmyquant.cli list strategies

# 列出所有因子
python -m ohmyquant.cli list factors
```

---

## 策略开发指南

### 策略类型总览

| 策略 | 版本 | 选股方法 | 适用场景 |
|------|------|----------|----------|
| `industry_rotation` | v66 | 行业轮动+多因子 | 60+120日动量+10因子评分+大盘过滤+港股持仓+正交化 |
| `expertForest` | v1 | 多专家集成 | 32个专家(momentum/fundamental/wavelet/volatility)投票集成,沪深300股票池 |

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
from __future__ import annotations

from ohmyquant.engine.base import BacktestResult
from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy

@register_strategy("mystrategy", "v1")
class MyStrategyV1(BaseStrategy):
    """我的策略 v1"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "MyStrategyV1":
        if strategy_type != "mystrategy" or version != "v1":
            raise ValueError(f"不支持: {strategy_type} {version}")

        # 使用 BaseStrategy._load_config_yaml 加载 config.yaml 并深度合并
        base_config = cls._load_config_yaml(config)
        return cls(base_config)
```

策略的 `run()` 和 `get_latest_positions()` 默认使用 `BaseStrategy` 提供的实现（通过 `StrategyRunner` 运行回测）。如需自定义回测流程，重写 `run()` 方法即可。

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
  method: industry_rotation
  top_n: 20
factors: [mom_1m, mom_3m, vol_20d]
pools:
  main: ["600519.SH", "601318.SH"]
data:
  source: duckdb
  data_root: os.getenv("DATA_ROOT", "data")
```

### 选股器

| 选股器 | method | 说明 | 适用场景 |
|--------|--------|------|----------|
| IndustryRotationSelector | `industry_rotation` | 行业轮动+多因子评分+大盘趋势过滤 | 行业轮动策略 |

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

@register_factor()  # 自动从类属性读取 name, category
class MyFactor(Factor):
    """自定义因子说明"""

    name = "my_factor"
    category = "custom"
    description = "我的自定义因子"
    direction = 1   # 1=正向（值大→收益高），-1=反向
    required_fields = ["close", "volume"]
    params = {"window": 20}  # 可配置参数，运行时用 config 覆盖
    depends_on = []          # 依赖的其他因子名
    version = "v1"           # 因子版本

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        volume = data["volume"]
        date_col = close["date"]
        close_num = close.drop("date")
        vol_num = volume.drop("date")
        window = self.params["window"]

        # 计算因子值（返回 date × code 宽表）
        result = (close_num * vol_num).select(
            [pl.col(c).rolling_mean(window_size=window).alias(c) for c in close_num.columns]
        )
        return result.insert_column(0, date_col)
```

> 放入 `factors/builtin/` 目录即可自动注册，无需修改 `__init__.py`。

#### 因子高级特性

```python
# 参数化因子 — 运行时覆盖窗口期
factor = FactorRegistry.create("mom_1m", config={"window": 15})

# LRU 缓存 — 避免重复计算
lib = FactorLibrary(config={"use_cache": True, "cache_size": 64})

# 外部因子 — 从外部目录加载
lib = FactorLibrary(config={"external_paths": ["path/to/my_factors"]})

# 因子依赖 — 自动解析
class MyFactor(Factor):
    depends_on = ["mom_1m"]  # FactorLibrary 会自动先计算 mom_1m

# 因子报告 — 一键生成分析
gen = FactorReportGenerator()
report = gen.generate("mom_1m", factor_values, forward_returns, close=close_df)
gen.save(report, "reports/mom_1m.md")
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

## Walk-Forward 验证

框架内置 walk-forward 验证管道（`optimization/walk_forward.py`），将回测区间切分为连续测试窗口，独立运行策略并评估绩效的跨周期稳定性：

- 跨牛熊周期是否持续盈利
- Sharpe 是否稳定为正
- 是否存在特定区间失效

```bash
# 跨周期验证 industry_rotation v66
omq optimize walk-forward industry_rotation v66 --window 1Y --step 1Y
```

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
strategy_type: industry_rotation
strategy_version: v66
strategy_name: "行业轮动策略 v66"

# 回测配置
backtest:
  start_date: "2015-01-01"
  end_date: "2024-12-31"
  data_start_date: "2010-01-01"   # 因子计算需要更早的数据
  transaction_cost: 0.001
  train_end: "2024-12-31"         # IC 分析的训练集截止日

# 选股配置
selection:
  method: industry_rotation  # industry_rotation
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
  method: equal           # equal
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
  data_root: os.getenv("DATA_ROOT", "data")
```

---

## CLI 命令行工具

```bash
# 运行策略
omq run industry_rotation v66
omq run industry_rotation v66 --config custom.yaml

# 执行回测（指定日期）
omq backtest --strategy industry_rotation --version v66 --start 2020-01-01 --end 2024-12-31

# 分析结果
omq analyze --results results.json --metrics
omq analyze --results r1.json --compare r2.json --report report.html

# 列出可用资源
omq list strategies
omq list factors
omq list data_sources

# 初始化策略（创建在 ohmyquant/strategy/strategies/ 下）
omq init my_strategy --type strategy
omq init my_strategy --type strategy --version v2

# 配置管理
omq config show
omq config set --key data.source --value duckdb
omq config reset

# 策略对比（多策略时可用）
# omq compare output/strategy_a/results.json output/strategy_b/results.json --report output/comparison.html

# 多策略集成（多策略时可用）
# omq ensemble strategy_a strategy_b --weighting perf_weight

# 策略优化
omq optimize walk-forward industry_rotation v66 --window 1Y --step 1Y
omq optimize param-search industry_rotation v66 --params '{"top_n": [20, 50, 100]}' --n-trials 30

# 获取最新持仓信号
omq signal industry_rotation v66
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

### CI/CD 与代码质量

- **GitHub Actions** (`.github/workflows/test.yml`): Python 3.10/3.11/3.12 矩阵测试 + ruff lint
- **Pre-commit hooks** (`.pre-commit-config.yaml`): ruff + ruff-format + 基础检查

```bash
# 安装 pre-commit hooks
pip install pre-commit
pre-commit install

# 手动运行
pre-commit run --all-files
```

### 测试覆盖

| 测试文件 | 覆盖模块 | 测试数 |
|----------|----------|--------|
| test_core.py | 插件系统、配置加载 | 8 |
| test_strategy.py | 策略注册、版本管理 | 5 |
| test_backtest.py | 成本模型、执行器、引擎 | 6 |
| test_analysis.py | 绩效指标、对比、显著性 | 11 |
| test_ths_utils.py | THS 工具函数 | 20 |
| test_rebalancer.py | 调仓器（3种+工厂） | 23 |
| test_scheduler.py | 调度器（Calendar+Adaptive） | 17 |
| test_selector.py | 选股器（权重上限+IC筛选） | 18 |
| test_factors.py | 因子计算+参数化+缓存+依赖+版本+报告 | 60 |
| test_walk_forward.py | Walk-Forward 窗口切分 | 17 |
| **合计** | **10/10 文件覆盖** | **187** |

### 批量分析与验证

```bash
# 行业轮动 T 日早晨调仓检查 + 生成同花顺交易文件
python scripts/industry_rotation/industry_rotation_daily.py

# 行业轮动 IS/OOS 回测
python scripts/industry_rotation/industry_rotation_is.py --version v66
python scripts/industry_rotation/industry_rotation_oos.py --version v66

# expertForest_v1 IS/OOS 验证
python scripts/expertforest_v1/expertforest_v1_is_explore.py --pool 000300 --top_n 30
python scripts/expertforest_v1/expertforest_v1_oos_validate.py

# 详细脚本说明见 scripts/README.md
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
│   │   ├── selectors/            #   1 种选股器
│   │   ├── allocator.py           #   分配器（HRP/EW/RP）
│   │   ├── risk_managers.py      #   风控管理器
│   │   └── portfolio.py          #   组合优化器
│   ├── strategy/                 # 策略管理
│   │   ├── base.py               #   BaseStrategy
│   │   ├── registry.py           #   StrategyRegistry
│   │   ├── runner.py             #   StrategyRunner
│   │   └── strategies/           # 2 个策略(industry_rotation v66, expertForest v1)
│   ├── execution/                # 执行系统
│   │   ├── cost_model.py         #   交易成本模型
│   │   ├── rebalancer.py         #   调仓器
│   │   ├── scheduler.py          #   调仓调度器
│   │   └── ths_utils.py          #   同花顺交易文件生成工具(跨策略复用)
│   ├── optimization/             # 策略优化
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
│   ├── cli/                      # 命令行工具
│   └── config/                   # 默认配置
├── scripts/                      # 辅助脚本
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

source = DuckDBSource({"data_root": os.getenv("DATA_ROOT", "data")})
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

### Q: 如何添加新的数据源？

A: 实现 `DataSource` ABC 的所有抽象方法，用 `@register_data_source("my_source")` 注册，然后在 config 中指定 `source: my_source`。

---

## Changelog

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## License

MIT
