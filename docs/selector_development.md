# 选股器开发指南

## BaseSelector 契约

所有选股器继承 [BaseSelector](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selector.py) 抽象基类，实现两个方法：

### select() — 选股

```python
def select(
    self,
    factors: dict[str, pl.DataFrame],    # {factor_name: date×code 宽表}
    ic_df: pl.DataFrame,                  # IC 数据
    stock_codes: list[str],               # 候选股票代码
    current_idx: int,                     # 当前时间索引
    close: pl.DataFrame,                  # 收盘价宽表
    regime: str | None = None,            # 市场状态
    strong_factors: list[str] | None = None,  # 强因子列表
    **kwargs,
) -> dict[str, float] | None:
    """返回 {code: weight} 或 None"""
```

### select_strong_factors() — 筛选强因子

```python
def select_strong_factors(
    self,
    ic_df: pl.DataFrame,
    train_end: str,
) -> list[str]:
    """返回强因子名列表"""
```

### 内置配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `top_n` | 10 | 选股数量 |
| `max_stock_weight` | 0.025 | 个股权重上限 |
| `ic_decay` | 0.65 | IC 衰减系数 |
| `icir_window` | 60 | ICIR 计算窗口 |

## 注册选股器

```python
from ..selector import BaseSelector
from ...core.plugin_system import register_selector


@register_selector("my_selector")
class MySelector(BaseSelector):
    """自定义选股器"""

    def select(self, factors, ic_df, stock_codes, current_idx, close, **kwargs):
        # 按因子值排名选股
        factor_values = factors["mom_1m"]
        current_row = factor_values.row(current_idx, named=True)
        scores = {c: current_row[c] for c in stock_codes if c in current_row}
        sorted_codes = sorted(scores, key=scores.get, reverse=True)[:self.top_n]
        weights = {c: 1.0 / self.top_n for c in sorted_codes}
        return self.apply_weight_cap(weights)

    def select_strong_factors(self, ic_df, train_end):
        return list(ic_df.columns[1:])
```

文件放入 [engine/selectors/](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/) 即自动注册。

## 7 种内置选股器

| 选股器 | method 配置值 | 适用场景 |
|--------|--------------|----------|
| ICIRSelector | `icir` | 基于因子 ICIR 加权选股，适合多因子模型基线 |
| MomentumSelector | `momentum` | 纯动量排名选股，适合趋势市场 |
| HybridSelector | `hybrid` | ICIR + 动量混合，兼顾因子有效性和趋势信号 |
| AdaptiveICIRSelector | `adaptive_icir` | 按市场状态自适应调整 ICIR 参数 |
| MLSelector | `ml` | 基于 ML 模型（LightGBM 等）选股 |
| ModelSelector | `model` | 基于 DL 模型（LSTM 等）选股 |
| RLSelector | `rl` | 基于 RL 模型（PPO 等）组合管理 |

### 配置切换

在策略 `config.yaml` 中通过 `selection.method` 切换：

```yaml
selection:
  method: icir          # 选股器名
  top_n: 50             # 选股数量
  max_stock_weight: 0.02
```

## 权重截断

`BaseSelector.apply_weight_cap()` 提供迭代截断逻辑，确保个股权重不超过 `max_stock_weight`：

```python
weights = {"A": 0.10, "B": 0.05, "C": 0.03}
capped = self.apply_weight_cap(weights, cap=0.05)
# {"A": 0.05, "B": 0.05, "C": 0.03} → 归一化后 {"A": 0.385, "B": 0.385, "C": 0.231}
```

## 选股器与策略的关系

选股器在 [BacktestEngine](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py) 中被调用：

```
BacktestEngine.run()
  └── 每个调仓日:
        ├── 计算因子值 → factors dict
        ├── 计算 IC → ic_df
        ├── selector.select(factors, ic_df, ...) → {code: weight}
        ├── risk_manager.apply(weights) → 调整后权重
        ├── allocator.allocate(weights) → 最终权重
        └── rebalancer.decide(old, new) → 调仓决策
```

选股器只负责选出标的和初始权重，后续风控/分配/调仓由各自模块处理。
