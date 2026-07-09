# 策略迭代指南

本文档是策略迭代的核心操作手册，覆盖从「复制基线策略」到「产出优化版本」的完整流程。

## 迭代流程总览

```
1. 复制目录 (v1 → v2)
   ↓
2. 编辑 config.yaml (选股/因子/调仓参数)
   ↓
3. 新增因子 (如需) → 参考 factor_development.md
   ↓
4. Walk-Forward 验证 (跨周期稳定性)
   ↓
5. 参数搜索 (Optuna/网格)
   ↓
6. 策略对比 (v1 vs v2)
   ↓
7. 策略集成 (多策略组合)
```

---

## 步骤 1：复制策略目录

```bash
# 从 ycj/v1 复制到 ycj/v2
Copy-Item -Recurse ohmyquant/strategy/strategies/ycj/v1 ohmyquant/strategy/strategies/ycj/v2
```

修改 `strategy.py` 中的注册信息：

```python
@register_strategy("ycj", "v2")          # 改版本号
class YCJStrategyV2(BaseStrategy):        # 改类名
    # ...
    def from_version(cls, strategy_type, version, config=None):
        base_config = {
            "strategy_type": "ycj",
            "strategy_version": "v2",      # 改版本号
            # ...
        }
```

## 步骤 2：编辑 config.yaml

以 ycj/v1 → v2 为例，参考 [ycj/v2/config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/ycj/v2/config.yaml)：

```yaml
# 选股方法升级：icir → hybrid
selection:
  method: hybrid
  top_n: 100              # 50 → 100
  max_stock_weight: 0.015 # 0.02 → 0.015
  min_ic: 0.02
  min_ic_ir: 0.1

# 风控升级：固定波动率 → managed_vol
risk:
  target_vol: 0.20        # 0.25 → 0.20
  vol_trend_mode: managed_vol

# 分配升级：等权 → HRP
allocation:
  method: hrp
  lookback: 60

# 因子扩展：3 → 7
factors:
  - mom_1m
  - mom_3m
  - mom_6m
  - rev_5d        # 新增反转因子
  - rev_20d
  - vol_20d       # 新增波动率因子
  - vol_60d

# 股票池
pools:
  main:
    - "600519.SH"
    - "601318.SH"
    # ...

data:
  source: duckdb
  data_root: "D:/Work/Project/download_a_share/data"
```

### config.yaml 关键字段

| 字段 | 说明 | 可选值 |
|------|------|--------|
| `backtest.start_date` / `end_date` | 回测区间 | 日期字符串 |
| `selection.method` | 选股器 | icir/hybrid/momentum/adaptive_icir/ml/model/rl |
| `selection.top_n` | 选股数量 | 整数 |
| `risk.target_vol` | 目标波动率 | 0.1-0.4 |
| `risk.vol_trend_mode` | 波动率趋势模式 | managed_vol/固定 |
| `allocation.method` | 分配方法 | equal/hrp/icir_weighted |
| `rebalance.frequency` | 调仓频率 | daily/weekly/monthly/quarterly/adaptive |
| `rebalance.method` | 调仓方法 | cost_benefit/simple/none |
| `rebalance.cost_model.name` | 成本模型 | stock_cn/etf_cn/mixed_cn |
| `factors` | 因子列表 | 因子注册名 |

## 步骤 3：新增因子（如需）

参考 [factor_development.md](file:///d:/Work/Project/OhMyQuant/docs/factor_development.md)。在 [factors/builtin/](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/) 下新建 `.py` 文件，用 `@register_factor` 注册，然后在 config.yaml 的 `factors` 列表中引用。

## 步骤 4：Walk-Forward 验证

用 [StrategyWalkForward](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/walk_forward.py) 评估策略跨周期稳定性：

```python
from ohmyquant.optimization import StrategyWalkForward

wf = StrategyWalkForward(test_window="1Y", step="1Y")
report = wf.run("ycj", "v2")
print(report.summary())
```

输出示例：
```
============================================================
Walk-Forward 报告: ycj v2
窗口规格: test=1Y, step=1Y
窗口数: 9
------------------------------------------------------------
平均 Sharpe:          1.2345  (std=0.4567)
平均年化收益:         15.23%  (std=8.45%)
正 Sharpe 窗口:       7/9  (consistency=77.8%)
------------------------------------------------------------
各窗口明细:
  [0] 2015-01-05~2015-12-31 (243d) nav=1.1234 sharpe=0.89 ann_ret=12.34% max_dd=-8.45%
  [1] 2016-01-04~2016-12-30 (244d) nav=0.9876 sharpe=-0.23 ann_ret=-1.24% max_dd=-12.34%
  ...
============================================================
```

**评判标准**：consistency > 60% 且 mean_sharpe > 0.5 为可接受。

### 窗口规格

| 规格 | 含义 | 交易日 |
|------|------|--------|
| `"1Y"` | 1 年 | 252 |
| `"6M"` | 半年 | 126 |
| `"3M"` | 季度 | 63 |
| `"63D"` | 63 天 | 63 |
| 整数 | 直接指定天数 | N |

## 步骤 5：参数搜索

用 [ParamSearcher](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/param_search.py) 搜索最优超参（自动使用 Optuna，未安装时降级为网格搜索）：

```python
from ohmyquant.optimization import ParamSearcher

ps = ParamSearcher(n_trials=50, metric="sharpe")
report = ps.search("ycj", "v2", {
    "selection.top_n": {"type": "int", "low": 30, "high": 100, "step": 10},
    "risk.target_vol": {"type": "float", "low": 0.15, "high": 0.30, "step": 0.05},
    "rebalance.frequency": {"type": "categorical", "choices": ["monthly", "weekly"]},
})
print(report.summary())
print(f"最优参数: {report.best_params}")
```

### 参数空间规格

```python
# 整数
"selection.top_n": {"type": "int", "low": 20, "high": 100, "step": 10}

# 浮点数
"risk.target_vol": {"type": "float", "low": 0.1, "high": 0.4, "step": 0.05}

# 对数尺度浮点
"model.learning_rate": {"type": "float", "low": 0.001, "high": 0.1, "log": True}

# 分类
"rebalance.frequency": {"type": "categorical", "choices": ["monthly", "weekly", "daily"]}
```

参数路径用点号分隔（如 `selection.top_n`），会自动深合并到策略 yaml 基础配置。

## 步骤 6：策略对比

用 [StrategyComparator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/compare.py) 对比 v1 vs v2：

```python
import numpy as np
from ohmyquant.strategy import StrategyRunner
from ohmyquant.analysis import StrategyComparator

# 运行两个策略
r1 = StrategyRunner.run_strategy("ycj", "v1")
r2 = StrategyRunner.run_strategy("ycj", "v2")

# 对比
comparator = StrategyComparator({
    "ycj_v1": r1.backtest_result.daily_returns.to_numpy(),
    "ycj_v2": r2.backtest_result.daily_returns.to_numpy(),
})

# 指标对比表
print(comparator.get_comparison_table())

# 相关性矩阵
print(comparator.compute_correlation_matrix())

# 排名
print(comparator.rank_strategies(metric="sharpe_ratio"))
```

详细用法参考 [strategy_comparison.md](file:///d:/Work/Project/OhMyQuant/docs/strategy_comparison.md)。

## 步骤 7：策略集成

用 [StrategyEnsemble](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/ensemble.py) 将多个策略组合：

```python
from ohmyquant.optimization import StrategyEnsemble

ens = StrategyEnsemble(weighting="perf_weight")
ens.add_strategy("ycj", "v2")
ens.add_strategy("etf", "v1")

result = ens.run()
print(f"集成 Sharpe: {result.metrics.sharpe_ratio:.4f}")
print(f"成分权重: {[(c['strategy_type'], c['weight']) for c in result.constituents]}")
```

### 加权方式

| 方式 | 说明 |
|------|------|
| `equal` | 等权 1/N |
| `perf_weight` | 按 Sharpe 加权（w_i ∝ max(sharpe_i, 0)） |
| `ir_weight` | 按信息比率加权（需 benchmark_returns） |

## 迭代版本（子版本）

如果不想新建主版本，可以创建迭代版本（如 v2.1）：

```
strategies/ycj/v2/iterations/v2_1/
  ├── __init__.py
  ├── config.yaml
  └── strategy.py
```

运行时用 `StrategyRunner.run_strategy("ycj", "v2.1")`。

---

## CLI 命令

```bash
# 运行策略
omq run ycj v2

# 列出策略
omq list strategies

# Walk-Forward
omq optimize walk-forward ycj v2 --window 1Y --step 1Y

# 参数搜索
omq optimize param-search ycj v2 --params '{"selection.top_n": {"type": "int", "low": 30, "high": 80, "step": 10}}'

# 策略对比
omq compare output/v1_results.json output/v2_results.json --report output/comparison.html
```

## 最佳实践

1. **渐进迭代**：每次只改一个维度（选股/因子/风控），对比效果后再叠加。
2. **样本外验证**：Walk-Forward 的 consistency 比全周期 Sharpe 更重要。
3. **避免过拟合**：参数搜索的 n_trials 不宜过大，参数空间不宜过宽。
4. **成本意识**：调仓频率提升会增加成本，用 `cost_benefit` 调仓器自动权衡。
5. **命名约定**：人工策略命名 `dh`，量化策略命名 `ycj`，所有文件/目录/代码中统一。
