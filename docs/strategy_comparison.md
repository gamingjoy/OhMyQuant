# 策略对比与报告

## 策略对比器

[StrategyComparator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/compare.py) 提供多策略绩效对比、相关性分析和组合优化。

### 基本用法

```python
import numpy as np
from ohmyquant.strategy import StrategyRunner
from ohmyquant.analysis import StrategyComparator

# 运行多个策略
r1 = StrategyRunner.run_strategy("ycj", "v1")
r2 = StrategyRunner.run_strategy("ycj", "v2")
r3 = StrategyRunner.run_strategy("etf", "v1")

# 创建对比器
comparator = StrategyComparator({
    "ycj_v1": r1.backtest_result.daily_returns.to_numpy(),
    "ycj_v2": r2.backtest_result.daily_returns.to_numpy(),
    "etf_v1": r3.backtest_result.daily_returns.to_numpy(),
})

# 1. 指标对比表
table = comparator.get_comparison_table()
print(table)
```

输出（polars DataFrame）：

```
┌──────────┬───────────────┬───────────┬───────────┬──────────────┐
│ strategy ┆ total_return  ┆ sharpe    ┆ max_drawd ┆ win_rate     │
│ ---      ┆ ---           ┆ ---       ┆ own       ┆ ---          │
│ str      ┆ f64           ┆ f64       ┆ f64       ┆ f64          │
╞══════════╪═══════════════╪═══════════╪═══════════╪══════════════╡
│ ycj_v1   ┆ 0.4523        ┆ 0.8923    ┆ -0.1234   ┆ 0.5234       │
│ ycj_v2   ┆ 0.6234        ┆ 1.2345    ┆ -0.0987   ┆ 0.5456       │
│ etf_v1   ┆ 0.3456        ┆ 0.7654    ┆ -0.0876   ┆ 0.5123       │
└──────────┴───────────────┴───────────┴───────────┴──────────────┘
```

### 对比表指标

| 指标 | 说明 |
|------|------|
| total_return | 累计收益 |
| annualized_return | 年化收益 |
| annualized_volatility | 年化波动率 |
| sharpe_ratio | Sharpe 比率 |
| sortino_ratio | Sortino 比率 |
| calmar_ratio | Calmar 比率 |
| max_drawdown | 最大回撤 |
| win_rate | 胜率 |
| profit_factor | 盈亏比 |
| n_days | 交易天数 |

### 相关性分析

```python
# 相关性矩阵
corr = comparator.compute_correlation_matrix()
print(corr)

# 滚动相关性（60 日窗口）
rolling = comparator.compute_rolling_correlation("ycj_v1", "ycj_v2", window=60)

# 找相关性最低的策略对（分散化效果最好）
pairs = comparator.find_best_pairs(top_n=3)
for p in pairs:
    print(f"{p['strategy1']} vs {p['strategy2']}: corr={p['correlation']:.4f}")
```

### 组合优化

```python
# 按权重组合策略
combined = comparator.combine_strategies({"ycj_v1": 0.4, "ycj_v2": 0.6})

# 两策略最优权重（目标波动率 20%）
weights = comparator.optimize_pair_allocation("ycj_v1", "ycj_v2", target_vol=0.2)
print(weights)  # {"ycj_v1": 0.45, "ycj_v2": 0.55}
```

### 策略排名

```python
# 按 Sharpe 排名
ranking = comparator.rank_strategies(metric="sharpe_ratio")
for name, value in ranking:
    print(f"{name}: {value:.4f}")

# 按最大回撤排名（越小越好）
ranking = comparator.rank_strategies(metric="max_drawdown")
```

---

## 报告生成

[ReportGenerator](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/report.py) 生成文本/Markdown/HTML 报告。

### HTML 报告

```python
import numpy as np
from ohmyquant.analysis import ReportGenerator

returns = np.array([0.01, -0.02, 0.03, ...])

generator = ReportGenerator(
    strategy_name="YCJ 量化策略",
    strategy_version="v2",
)

# 生成 HTML 报告（含净值曲线、回撤曲线、收益分布图）
generator.generate_html_report(returns, output_path="output/report.html")
```

HTML 报告包含：
- 策略概览
- 完整绩效指标表（18 项指标）
- 净值曲线（Plotly 交互图）
- 回撤曲线
- 收益分布直方图

### 文本 / Markdown 报告

```python
# 文本报告
text = generator.generate_text_report(returns, output_path="output/report.txt")

# Markdown 报告
md = generator.generate_markdown_report(returns, output_path="output/report.md")
```

---

## 统计显著性检验

[SignificanceTester](file:///d:/Work/Project/OhMyQuant/ohmyquant/analysis/significance.py) 检验策略收益的统计显著性。

### t 检验

```python
from ohmyquant.analysis import SignificanceTester

tester = SignificanceTester(returns)

# 检验超额收益是否显著不为零
result = tester.t_test(benchmark_returns=None)
print(f"t统计量: {result.t_statistic:.4f}")
print(f"p值: {result.p_value:.4f}")
# p < 0.05 → 收益显著不为零
```

### Bootstrap Sharpe 置信区间

```python
result = tester.bootstrap_sharpe(n_samples=1000, confidence=0.95)
print(f"Sharpe: {result.sharpe_ratio:.4f}")
print(f"95% CI: ({result.bootstrap_sharpe_ci[0]:.4f}, {result.bootstrap_sharpe_ci[1]:.4f})")
```

### Deflated Sharpe Ratio (DSR)

多重检验校正后的 Sharpe 比率，防止「多次试验取最优」的过拟合偏差：

```python
result = tester.deflated_sharpe_ratio(num_trials=100, n_samples=1000)
print(f"DSR: {result.dsr:.4f}")
# DSR < 0.05 → Sharpe 在多重检验下仍显著
```

### 一次性运行所有检验

```python
result = tester.run_all(benchmark_returns=None, num_trials=100)
tester.print_results()
```

输出：
```
============================================================
统计显著性测试
============================================================
t统计量:              2.3456
p值:                  0.0189
Sharpe 比率:          1.2345
Bootstrap 95% CI:  (0.8765, 1.5678)
DSR:                  0.0345
============================================================
```

---

## CLI 命令

```bash
# 对比两个策略结果 JSON
omq compare output/v1_results.json output/v2_results.json --report output/comparison.html

# 分析单个结果
omq analyze --results output/results.json --metrics --report output/report.html
```

> **注意**：`compare` 和 `report` 命令依赖 result JSON 中包含 `daily_returns` 数组。确保使用 `omq run` 或 `omq backtest` 时已正确持久化。
