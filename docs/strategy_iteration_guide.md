# 策略迭代指南

本文档是策略迭代的核心操作手册，覆盖从「复制基线策略」到「产出优化版本并锁定」的完整流程。

## 迭代流程总览

```
 1. 确定数据划分 (IS/OOS)          ← 防前视偏差，最优先
    ↓
 2. 复制策略目录 (v_prev → v_new)
    ↓
 3. 编辑 config.yaml + strategy.py
    ↓
 4. 新增因子 (如需) → 参考 factor_development.md
    ↓
 5. IS 候选池对比 (如需)            ← 用 IS 数据选池
    ↓
 6. IS 超参搜索 (网格/Optuna)       ← 用 IS 数据搜参
    ↓
 7. OOS 最终验证                    ← 只验证，不调参
    ↓
 8. 持仓分析 (行业/换手/权重)
    ↓
 9. 策略对比 (v_prev vs v_new)
    ↓
10. 文档更新 (报告 + 总结)
    ↓
11. 归档旧版本 + Git 提交
    ↓
12. 收敛判断 (IS+OOS 双优 → final)
```

---

## 步骤 1：确定数据划分 (IS/OOS)

> **这是最重要的步骤**。所有参数选择必须基于 IS 数据，OOS 仅做最终验证。

### 数据划分原则

| 数据集 | 用途 | 说明 |
|--------|------|------|
| **IS（样本内）** | 模型训练、参数搜索、候选池选择 | 回测区间 + 训练数据 |
| **OOS（样本外）** | 最终验证，**不调任何参数** | 仅看结果 |

### mlf 策略的数据划分

```
数据起始: 2018-01-01 (因子数据从2018开始)
IS 回测:  2022-01-01 ~ 2025-12-31 (4年，data_start=2018保证训练窗口)
OOS 回测: 2026-06-01 ~ 2026-07-10 (样本外，仅验证)
```

### 配置方式

```python
# IS 回测配置
strategy.config.backtest.start_date = "2022-01-01"      # IS 起点
strategy.config.backtest.end_date = "2025-12-31"         # IS 终点
strategy.config.backtest.data_start_date = "2018-01-01"  # 训练数据起点

# OOS 回测配置 (最终验证时)
strategy.config.backtest.start_date = "2026-06-01"       # OOS 起点
strategy.config.backtest.end_date = "2026-07-10"         # OOS 终点
strategy.config.backtest.data_start_date = "2018-01-01"  # 训练数据不变
```

**关键规则**: IS 和 OOS 的 `data_start_date` 相同（ML训练需要历史数据），但回测区间不重叠。

参考: [mlf_is_pool_compare.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_is_pool_compare.py)、[mlf_is_gridsearch.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_is_gridsearch.py)

---

## 步骤 2：复制策略目录

```bash
# 从 mlf/v5 复制到 mlf/v9
Copy-Item -Recurse ohmyquant/strategy/strategies/mlf/v5 ohmyquant/strategy/strategies/mlf/v9
```

修改 `strategy.py` 中的注册信息：

```python
@register_strategy("mlf", "v9")           # 改版本号
class MLFStrategyV9(BaseStrategy):         # 改类名
    # ...
    def from_version(cls, strategy_type, version, config=None):
        base_config = {
            "strategy_type": "mlf",
            "strategy_version": "v9",       # 改版本号
            # ...
        }
```

同时修改 `__init__.py`：

```python
"""ML 选因子策略 v9"""
from .strategy import MLFStrategyV9
__all__ = ["MLFStrategyV9"]
```

---

## 步骤 3：编辑 config.yaml

以 mlf/v8 为例，参考 [mlf/v8/config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/mlf/v8/config.yaml)：

```yaml
selection:
  method: mlf
  top_n: 20                # 选股数量
  max_stock_weight: 0.04   # 单股上限
  mlf:
    top_k_factors: 30      # ML选因子数
    train_window: 1008     # 训练窗口(天)
    retrain_freq: 21       # 重训练频率
    max_industry_weight: 0.25  # 行业暴露上限

pools:
  stocks:
    index: "000300.XSHG"   # 候选池指数

factors:
  - mom_1m                 # 因子列表(mlf用预计算因子，这里仅占位)
```

### config.yaml 关键字段

| 字段 | 说明 | 可选值 |
|------|------|--------|
| `backtest.start_date` / `end_date` | 回测区间 | 日期字符串 |
| `selection.method` | 选股器 | icir/hybrid/momentum/mlf |
| `selection.top_n` | 选股数量 | 整数 |
| `selection.max_stock_weight` | 单股权重上限 | 0.02-0.05 |
| `risk.target_vol` | 目标波动率 | 0.1-0.4 |
| `rebalance.frequency` | 调仓频率 | daily/weekly/monthly |
| `rebalance.method` | 调仓方法 | cost_benefit/simple/none |
| `pools.stocks.index` | 候选池指数代码 | 000300/000819/000905 等 |

---

## 步骤 4：新增因子（如需）

参考 [factor_development.md](file:///d:/Work/Project/OhMyQuant/docs/factor_development.md)。在 [factors/builtin/](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/) 下新建 `.py` 文件，用 `@register_factor` 注册。

> mlf 策略使用 jqdata 预计算的 260 个因子，不需要此步骤。

---

## 步骤 5：IS 候选池对比

> 用 IS 数据对比不同候选池，选择 IS 表现更优的池。**不要用 OOS 结果选池**。

### 可用候选池

| 指数代码 | 名称 | 股票数 | 类型 |
|----------|------|--------|------|
| 000016.XSHG | 上证50 | 50 | 超大盘 |
| 000300.XSHG | 沪深300 | 300 | 大盘 |
| 000905.XSHG | 中证500 | 500 | 中盘 |
| 000819.XSHG | 中证800 | 800 | 大+中盘 |
| 000852.XSHG | 中证1000 | 1000 | 小盘 |

### 对比脚本

参考 [mlf_is_pool_compare.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_is_pool_compare.py)：

```python
# IS 回测配置
strategy.config.backtest.start_date = "2022-01-01"
strategy.config.backtest.end_date = "2025-12-31"
strategy.config.backtest.data_start_date = "2018-01-01"
strategy.config.pools = {"stocks": {"index": "000300.XSHG"}}  # 改池子
```

### mlf 经验

沪深300 IS Sharpe 0.18 > 中证800 IS Sharpe 0.16，且中证800导致 ML 选到周期股（OOS崩盘）。**大盘股池更稳定**。

---

## 步骤 6：IS 超参搜索

> 用 IS 数据搜索超参，选择 IS 表现最优的配置。

### 搜索方式

**方式一：自定义网格搜索**（推荐，可控性强）

参考 [mlf_is_gridsearch.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_is_gridsearch.py)：

```python
COMBOS = [
    {"label": "n20_k30_ind25", "top_n": 20, "top_k": 30, "ind_cap": 0.25},
    {"label": "n30_k25_ind20", "top_n": 30, "top_k": 25, "ind_cap": 0.20},
    # ...
]

for combo in COMBOS:
    strategy.config.selection.top_n = combo["top_n"]
    strategy.config.selection.mlf["top_k_factors"] = combo["top_k"]
    strategy.config.selection.mlf["max_industry_weight"] = combo["ind_cap"]
    # 运行 IS 回测...
```

**方式二：ParamSearcher**（Optuna/网格自动搜索）

```python
from ohmyquant.optimization import ParamSearcher

ps = ParamSearcher(n_trials=50, metric="sharpe")
report = ps.search("mlf", "v9", {
    "selection.top_n": {"type": "int", "low": 20, "high": 40, "step": 10},
    "selection.mlf.top_k_factors": {"type": "int", "low": 20, "high": 30, "step": 5},
})
```

### 搜索原则

1. **只在 IS 上搜索** — OOS 数据不参与参数选择
2. **组合数不宜过多** — IS 回测慢（mlf约15分钟/次），3-9个关键组合即可
3. **避免过拟合** — 参数空间不宜过宽，围绕基线小幅调整

---

## 步骤 7：OOS 最终验证

> 用 IS 选出的最优配置，在 OOS 期间回测。**只看结果，不调参数**。

参考 [mlf_v8_oos.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_v8_oos.py)：

```python
# OOS 回测配置
strategy.config.backtest.start_date = "2026-06-01"   # OOS 起点
strategy.config.backtest.end_date = "2026-07-10"      # OOS 终点
# 超参使用 IS 搜索的最优值，不再调整
```

### 验证标准

| 检查项 | 通过标准 |
|--------|----------|
| OOS 收益为正 | total_return > 0 |
| OOS Sharpe 合理 | sharpe > 0.5 (短期可更高) |
| IS/OOS 一致性 | IS 最优 = OOS 最优 |
| 无极端回撤 | max_drawdown > -15% |

**如果 OOS 表现极差**: 说明 IS 搜索过拟合，需减少参数组合数或缩小搜索范围。

---

## 步骤 8：持仓分析

分析建仓/调仓的持仓明细、行业分布、换手率。

参考 [mlf_position_analysis.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_position_analysis.py)：

```python
# 分析内容
- 股票只数、总权重、权重范围
- 行业分布（各行业权重占比）
- 换手率（调仓新增/剔除股票数）
- 单股权重分布
```

### 分析要点

| 检查项 | 关注点 |
|--------|--------|
| 行业集中度 | 单行业占比是否过高 (>40%需关注) |
| 换手率 | 月度换手是否合理 (0-30%正常) |
| 权重分布 | 是否有股权重过大 (>5%需关注) |
| 总仓位 | 是否有大量现金 (>20%需关注) |

---

## 步骤 9：策略对比

用 [StrategyComparator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/compare.py) 对比 v_prev vs v_new：

```python
from ohmyquant.strategy import StrategyRunner
from ohmyquant.analysis import StrategyComparator

r1 = StrategyRunner.run_strategy("mlf", "v5")
r2 = StrategyRunner.run_strategy("mlf", "v8")

comparator = StrategyComparator({
    "v5": r1.backtest_result.daily_returns.to_numpy(),
    "v8": r2.backtest_result.daily_returns.to_numpy(),
})
print(comparator.get_comparison_table())
print(comparator.rank_strategies(metric="sharpe_ratio"))
```

### 对比维度

| 维度 | 说明 |
|------|------|
| 总收益/年化收益 | 绝对回报 |
| Sharpe/Calmar | 风险调整回报 |
| 最大回撤 | 极端风险 |
| 胜率 | 盈利稳定性 |
| IS vs OOS | 是否一致 |

---

## 步骤 10：文档更新

### 10.1 更新策略报告

编辑 [docs/mlf_strategy_report.md](file:///d:/Work/Project/OhMyQuant/docs/mlf_strategy_report.md)：

1. 更新顶部 final 版本信息
2. 在版本历史表（2.2节）添加新版本行
3. 在 IS 验证表（2.4节）添加新组合结果
4. 更新迭代思路（第3节）

### 10.2 更新总结文档

编辑 [docs/mlf_strategy_summary.md](file:///d:/Work/Project/OhMyQuant/docs/mlf_strategy_summary.md)：

1. 更新迭代路线图
2. 更新核心指标对比表
3. 更新最终配置表

### 文档命名规范

| 文档 | 命名 | 内容 |
|------|------|------|
| 详细报告 | `{strategy}_strategy_report.md` | 完整迭代记录 |
| 总结文档 | `{strategy}_strategy_summary.md` | 一页纸概览 |

---

## 步骤 11：归档旧版本 + Git 提交

### 11.1 归档旧版本

```bash
# 归档非 final 的旧版本
mv ohmyquant/strategy/strategies/mlf/v_old archive/strategies/mlf/v_old

# 归档旧脚本
mv scripts/mlf_v_old_oos.py archive/scripts/mlf_v_old_oos.py
```

**保留规则**: 主目录只保留当前 final 和前一版 final（用于对比）。

### 11.2 Git 提交

```bash
git add -A
git commit -m "feat: add mlf_v9 strategy (IS+OOS validated)" \
           -m "v9 config: n20_k30_ind25, IS Sharpe 0.52, OOS Sharpe 5.39"
```

### Commit message 规范

| 前缀 | 用途 |
|------|------|
| `feat:` | 新策略版本/新功能 |
| `fix:` | 修复 bug |
| `refactor:` | 代码重构/归档 |
| `docs:` | 文档更新 |

---

## 步骤 12：收敛判断

### 策略收敛标准

| 标准 | 说明 |
|------|------|
| IS 最优 = OOS 最优 | 同一配置在 IS 和 OOS 都最优 |
| IS Sharpe > 0.3 | 样本内表现合理 |
| OOS 收益为正 | 样本外验证通过 |
| 无过拟合迹象 | 参数组合数合理，IS/OOS 一致 |

### 收敛后操作

1. 在策略 `strategy.py` 的 docstring 标注 `final`
2. 在报告版本历史表标注 `**final**`
3. 在总结文档更新"当前最终版本"
4. 归档所有非 final 旧版本
5. Git 提交

### 未收敛时

如果 OOS 表现差或 IS/OOS 不一致：
- 减少参数组合数（降低过拟合风险）
- 检查候选池是否合适
- 检查是否有前视偏差
- 考虑策略思路是否需要调整

---

## 附：Walk-Forward 验证（可选）

用 [StrategyWalkForward](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/walk_forward.py) 评估策略跨周期稳定性：

```python
from ohmyquant.optimization import StrategyWalkForward

wf = StrategyWalkForward(test_window="1Y", step="1Y")
report = wf.run("mlf", "v8")
print(report.summary())
```

**评判标准**: consistency > 60% 且 mean_sharpe > 0.5 为可接受。

---

## 附：策略集成（可选）

用 [StrategyEnsemble](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/ensemble.py) 组合多策略：

```python
from ohmyquant.optimization import StrategyEnsemble

ens = StrategyEnsemble(weighting="perf_weight")
ens.add_strategy("mlf", "v8")
ens.add_strategy("etf", "v1")
result = ens.run()
```

---

## CLI 命令

```bash
# 运行策略
omq run mlf v8

# 列出策略
omq list strategies

# Walk-Forward
omq optimize walk-forward mlf v8 --window 1Y --step 1Y

# 参数搜索
omq optimize param-search mlf v8 --params '{"selection.top_n": {"type": "int", "low": 20, "high": 40, "step": 10}}'

# 策略对比
omq compare output/v5_results.json output/v8_results.json --report output/comparison.html
```

---

## 最佳实践

1. **IS/OOS 严格划分** — 所有参数选择基于 IS，OOS 仅验证（防前视偏差）
2. **渐进迭代** — 每次只改一个维度（选股/因子/风控），对比效果后再叠加
3. **大盘股池优先** — 沪深300比中证800更稳定（mlf经验）
4. **避免过拟合** — 参数组合数不超过9个，围绕基线小幅调整
5. **成本意识** — 调仓频率提升会增加成本，用 `cost_benefit` 调仓器自动权衡
6. **及时归档** — 非 final 版本及时移至 archive/，主目录只保留2个版本
7. **文档同步** — 每次迭代后更新报告和总结，确保可复现
8. **命名约定**:
   - ML选因子策略: `mlf` (Machine Learning Factor selection)
   - 版本号 `v1`, `v2`... 标注主迭代
   - 超参标签写入 description (如 `k30_w1008_csi300_n20_ind25`)
   - 收敛后标注 `final` 状态
   - 详见 [mlf_strategy_report.md](file:///d:/Work/Project/OhMyQuant/docs/mlf_strategy_report.md) 第2节
