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

### industry_rotation 策略的数据划分

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

**关键规则**: IS 和 OOS 的 `data_start_date` 相同（行业轮动需要历史数据计算动量/因子），但回测区间不重叠。

参考: [industry_rotation_is.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation_is.py)

---

## 步骤 2：复制策略目录

```bash
# 从 industry_rotation/v5 复制到 industry_rotation/v6
Copy-Item -Recurse ohmyquant/strategy/strategies/industry_rotation/v5 ohmyquant/strategy/strategies/industry_rotation/v6
```

修改 `strategy.py` 中的注册信息：

```python
@register_strategy("industry_rotation", "v6")           # 改版本号
class IndustryRotationStrategyV6(BaseStrategy):          # 改类名
    # ...
    def from_version(cls, strategy_type, version, config=None):
        base_config = {
            "strategy_type": "industry_rotation",
            "strategy_version": "v6",       # 改版本号
            # ...
        }
```

同时修改 `__init__.py`：

```python
"""行业轮动策略 v6"""
from .strategy import IndustryRotationStrategyV6
__all__ = ["IndustryRotationStrategyV6"]
```

---

## 步骤 3：编辑 config.yaml

以 industry_rotation/v5 为例，参考 [industry_rotation/v5/config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/industry_rotation/v5/config.yaml)：

```yaml
selection:
  method: industry_rotation
  top_n: 10                # 选股数量
  max_stock_weight: 0.10   # 单股上限
  industry_rotation:
    top_industries: 5            # 选中行业数
    stocks_per_industry: 2       # 每个行业选股数
    momentum_short: 60           # 短期动量窗口(天)
    momentum_long: 120           # 长期动量窗口(天)
    weight_short: 0.6            # 短期动量权重
    weight_long: 0.4             # 长期动量权重
    max_industry_weight: 0.30    # 行业暴露上限
    market_filter: true          # 大盘趋势过滤
    market_index: "000300.XSHG"  # 大盘参考指数
    market_ma_short: 10          # 大盘短期均线
    market_ma_long: 20           # 大盘长期均线

pools:
  stocks:
    index: "000300.XSHG"   # 候选池指数

factors:
  - mom_1m                 # 因子列表(industry_rotation用factor_names内定义的多因子)
```

### config.yaml 关键字段

| 字段 | 说明 | 可选值 |
|------|------|--------|
| `backtest.start_date` / `end_date` | 回测区间 | 日期字符串 |
| `selection.method` | 选股器 | industry_rotation |
| `selection.top_n` | 选股数量 | 整数 |
| `selection.max_stock_weight` | 单股权重上限 | 0.02-0.10 |
| `risk.target_vol` | 目标波动率 | 0.1-0.4 |
| `rebalance.frequency` | 调仓频率 | daily/weekly/monthly |
| `rebalance.method` | 调仓方法 | cost_benefit/simple/none |
| `pools.stocks.index` | 候选池指数代码 | 000300/000819/000905 等 |

---

## 步骤 4：新增因子（如需）

参考 [factor_development.md](file:///d:/Work/Project/OhMyQuant/docs/factor_development.md)。在 [factors/builtin/](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/) 下新建 `.py` 文件，用 `@register_factor` 注册。

> industry_rotation 策略在 `selection.industry_rotation.factor_names` 中直接使用聚宽预计算的因子，不需要此步骤。

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

参考 [industry_rotation_is.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation_is.py)：

```python
# IS 回测配置
strategy.config.backtest.start_date = "2022-01-01"
strategy.config.backtest.end_date = "2025-12-31"
strategy.config.backtest.data_start_date = "2018-01-01"
strategy.config.pools = {"stocks": {"index": "000300.XSHG"}}  # 改池子
```

### 行业轮动经验

沪深300 IS Sharpe 0.18 > 中证800 IS Sharpe 0.16，且中证800导致动量选到周期股（OOS崩盘）。**大盘股池更稳定**。

---

## 步骤 6：IS 超参搜索

> 用 IS 数据搜索超参，选择 IS 表现最优的配置。

### 搜索方式

**方式一：自定义网格搜索**（推荐，可控性强）

参考 [industry_rotation_is.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation_is.py)：

```python
COMBOS = [
    {"label": "ind5_spi2_mom60_120", "top_industries": 5, "stocks_per_industry": 2, "mom_s": 60, "mom_l": 120},
    {"label": "ind4_spi3_mom60_120", "top_industries": 4, "stocks_per_industry": 3, "mom_s": 60, "mom_l": 120},
    # ...
]

for combo in COMBOS:
    strategy.config.selection.industry_rotation["top_industries"] = combo["top_industries"]
    strategy.config.selection.industry_rotation["stocks_per_industry"] = combo["stocks_per_industry"]
    strategy.config.selection.industry_rotation["momentum_short"] = combo["mom_s"]
    strategy.config.selection.industry_rotation["momentum_long"] = combo["mom_l"]
    # 运行 IS 回测...
```

**方式二：ParamSearcher**（Optuna/网格自动搜索）

```python
from ohmyquant.optimization import ParamSearcher

ps = ParamSearcher(n_trials=50, metric="sharpe")
report = ps.search("industry_rotation", "v6", {
    "selection.top_n": {"type": "int", "low": 10, "high": 20, "step": 5},
    "selection.industry_rotation.top_industries": {"type": "int", "low": 3, "high": 6, "step": 1},
    "selection.industry_rotation.momentum_long": {"type": "int", "low": 60, "high": 120, "step": 30},
})
```

### 搜索原则

1. **只在 IS 上搜索** — OOS 数据不参与参数选择
2. **组合数不宜过多** — IS 回测慢（industry_rotation约15分钟/次），3-9个关键组合即可
3. **避免过拟合** — 参数空间不宜过宽，围绕基线小幅调整

---

## 步骤 7：OOS 最终验证

> 用 IS 选出的最优配置，在 OOS 期间回测。**只看结果，不调参数**。

参考 [industry_rotation_oos.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation_oos.py)：

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

参考 [industry_rotation_daily.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation_daily.py)：

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

r1 = StrategyRunner.run_strategy("industry_rotation", "v4")
r2 = StrategyRunner.run_strategy("industry_rotation", "v5")

comparator = StrategyComparator({
    "v4": r1.backtest_result.daily_returns.to_numpy(),
    "v5": r2.backtest_result.daily_returns.to_numpy(),
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

编辑 [docs/industry_rotation_v6_strategy_report.md](file:///d:/Work/Project/OhMyQuant/docs/industry_rotation_v6_strategy_report.md)：

1. 更新顶部 final 版本信息
2. 在版本历史表（2.2节）添加新版本行
3. 在 IS 验证表（2.4节）添加新组合结果
4. 更新迭代思路（第3节）

### 10.2 文档命名规范

| 文档 | 命名 | 内容 |
|------|------|------|
| 详细报告 | `{type}_{version}_strategy_report.md` | 完整迭代记录 |

---

## 步骤 11：归档旧版本 + Git 提交

### 11.1 归档旧版本

```bash
# 归档非 final 的旧版本
mv ohmyquant/strategy/strategies/industry_rotation/v_old archive/strategies/industry_rotation/v_old

# 归档旧脚本
mv scripts/industry_rotation_v_old_oos.py archive/scripts/industry_rotation_v_old_oos.py
```

**保留规则**: 主目录只保留当前 final 和前一版 final（用于对比）。

### 11.2 Git 提交

```bash
git add -A
git commit -m "feat: add industry_rotation_v6 strategy (IS+OOS validated)" \
           -m "v6 config: ind5_spi2_mom60_120, IS Sharpe 0.52, OOS Sharpe 5.39"
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
report = wf.run("industry_rotation", "v5")
print(report.summary())
```

**评判标准**: consistency > 60% 且 mean_sharpe > 0.5 为可接受。

---

## 附：策略集成（可选）

用 [StrategyEnsemble](file:///d:/Work/Project/OhMyQuant/ohmyquant/optimization/ensemble.py) 组合多策略：

```python
from ohmyquant.optimization import StrategyEnsemble

ens = StrategyEnsemble(weighting="perf_weight")
ens.add_strategy("industry_rotation", "v5")
ens.add_strategy("industry_rotation", "v4")
result = ens.run()
```

---

## CLI 命令

```bash
# 运行策略
omq run industry_rotation v5

# 列出策略
omq list strategies

# Walk-Forward
omq optimize walk-forward industry_rotation v5 --window 1Y --step 1Y

# 参数搜索
omq optimize param-search industry_rotation v5 --params '{"selection.top_n": {"type": "int", "low": 10, "high": 20, "step": 5}}'

# 策略对比
omq compare output/v4_results.json output/v5_results.json --report output/comparison.html
```

---

## 最佳实践

1. **IS/OOS 严格划分** — 所有参数选择基于 IS，OOS 仅验证（防前视偏差）
2. **渐进迭代** — 每次只改一个维度（选股/因子/风控），对比效果后再叠加
3. **大盘股池优先** — 沪深300比中证800更稳定（行业轮动经验）
4. **避免过拟合** — 参数组合数不超过9个，围绕基线小幅调整
5. **成本意识** — 调仓频率提升会增加成本，用 `cost_benefit` 调仓器自动权衡
6. **及时归档** — 非 final 版本及时移至 archive/，主目录只保留2个版本
7. **文档同步** — 每次迭代后更新报告和总结，确保可复现
8. **命名约定** (统一规范):
   - **代码标识**: `{type}_{version}` (如 `industry_rotation_v5`)
     - `type` 为简短英文缩写: `industry_rotation`(行业轮动)...
     - `version` 标注主迭代: `v1`, `v2`...
   - **完整名**: `{type}_{version} ({超参标签}, {状态})` (如 `industry_rotation_v6 (mf12_lowbeta_mom60_120_mkt20, final)`)
     - 超参标签: 核心超参缩写 (如 `mf12`=12因子, `lowbeta`=含反向beta因子, `mom60_120`=60/120日动量, `mkt20`=大盘20日过滤)
     - 状态标记: `final`(已收敛) / `iter`(迭代中) / `abandoned`(已放弃)
   - **目录与文件命名** (所有位置统一用代码标识):
     - 策略代码: `ohmyquant/strategy/strategies/{type}/{version}/`
     - 同花顺输出: `output/ths/{type}_{version}/`
     - 策略报告: `docs/{type}_{version}_strategy_report.md`
     - 脚本: `scripts/{type}_*.py`
   - 收敛后标注 `final` 状态，写入 `strategy_name` 和 `description`
