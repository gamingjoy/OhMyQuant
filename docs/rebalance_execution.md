# 建仓调仓执行指南

## 概览

OhMyQuant 的调仓执行系统由四个可插拔组件组成：

```
Scheduler (何时调仓)
  ↓ 调仓日集合
Rebalancer (是否调仓 + 调仓决策)
  ↓ 买卖清单 + 最终权重
CostModel (调仓成本)
  ↓ 总成本占比
Executor (执行交易)
  ↓ 交易记录
```

## 成本模型

[CostModel](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/cost_model.py) 计算交易成本。3 种内置模型：

### stock_cn（A股）

```python
买入：佣金(万2.5) + 过户费(万0.1)
卖出：佣金(万2.5) + 印花税(万5) + 过户费(万0.1)
```

可配置费率：
```yaml
rebalance:
  cost_model:
    name: stock_cn
    commission_rate: 0.00025   # 佣金费率
    stamp_duty: 0.0005         # 印花税（卖出单边）
    transfer_fee: 0.00001      # 过户费
```

### etf_cn（ETF）

```python
买入：申购费（C类通常为0）
卖出：赎回费，持有 < 7 天为 1.5%，≥ 7 天为 0%
```

```yaml
rebalance:
  cost_model:
    name: etf_cn
    purchase_fee: 0.0
    redeem_fee_within_7d: 0.015
    redeem_fee_after_7d: 0.0
    min_hold_days: 7
```

### mixed_cn（A股+ETF混合）

按代码前缀自动判断资产类型（51/15/16/52/56/59 开头为 ETF），分别使用对应费率。用于 [etf/v2](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/etf/v2/config.yaml) 等混合策略。

```yaml
rebalance:
  cost_model:
    name: mixed_cn
```

### 自定义成本模型

参考 [plugin_hotplug.md](file:///d:/Work/Project/OhMyQuant/docs/plugin_hotplug.md)，在 [cost_model.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/cost_model.py) 中添加 `@register_cost_model("my_cost")` 类即可。

---

## 调仓器

[Rebalancer](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/rebalancer.py) 决定是否执行调仓及如何调仓。3 种内置调仓器：

### cost_benefit（成本收益权衡）

**默认推荐**。评估每个卖出候选的成本与预期收益提升，仅当净收益 > threshold 时执行调仓。

```yaml
rebalance:
  method: cost_benefit
  cost_benefit_threshold: 0.001   # 净收益阈值（0.1%）
  cost_model:
    name: stock_cn
```

决策逻辑：
1. 计算每个卖出候选的卖出成本
2. 估算预期收益提升 = (最佳买入评分 - 当前评分) × 0.1
3. 净收益 = 预期收益提升 - 卖出成本
4. 净收益 > threshold → 执行调仓；否则跳过（保留旧持仓）

跳过的标的保留在 `final_weights` 中，避免频繁调仓侵蚀收益。

### simple（简单调仓）

直接采用目标权重，不做成本收益权衡。仅计算交易成本。

```yaml
rebalance:
  method: simple
  cost_model:
    name: stock_cn
```

### none（不调仓）

保持当前持仓不变。用于回测中保持向后兼容。

---

## 调度器

[Scheduler](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/scheduler.py) 决定何时调仓。2 种内置调度器：

### calendar（日历调度）

按固定频率调仓：

```yaml
rebalance:
  frequency: monthly    # daily/weekly/monthly/quarterly
  weekday: 0            # 周几调仓（0=周一）
```

| 频率 | 说明 |
|------|------|
| daily | 每日 |
| weekly | 每周 |
| monthly | 每月首个交易日 |
| quarterly | 每季首个交易日 |

### adaptive（自适应调度）

日历频率 + 波动率触发：近期年化波动率超阈值时追加调仓日。

```yaml
rebalance:
  frequency: adaptive
  vol_threshold: 0.3       # 波动率触发阈值
  lookback: 20             # 回看窗口（交易日）
  min_rebalance_interval: 5  # 最小调仓间隔（交易日）
```

---

## 执行器

[Executor](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/executor.py) 执行交易。2 种内置执行器：

### simulated（模拟执行）

回测用。记录交易到 `trade_log`，不实际执行。

```python
from ohmyquant.execution import create_executor, BaseExecutor

executor = create_executor({"mode": "simulated"})
trades = BaseExecutor.compute_trades(old_weights, new_weights)
result = executor.execute_trades(trades, "2024-01-15", old_weights)
```

### live（实盘执行）

预留接口，对接券商 API 时实现。当前抛出 `NotImplementedError`。

---

## T 日工作流

用户实际操作流程（参考用户偏好）：

```
T 日早晨：
  1. 运行 python scripts/update_data.py
     → 下载 T-1 数据（当年全量 + 前一年）
     → 数据写入 D:/Work/Project/download_a_share/data/

T 日交易时段：
  2. 买入场外基金（按 T 日收盘价结算）
     → 无法获取盘中数据

T 日收盘后：
  3. 运行 omq run ycj v2
     → 回测验证策略效果
     → 结果保存到 output/results.json

  4. （可选）omq compare output/v1.json output/v2.json --report output/report.html
     → 对比策略效果
```

### 数据更新脚本

```bash
# 增量更新（T-1 数据 + 当年全量 + 前一年）
python scripts/update_data.py

# 预览不下载
python scripts/update_data.py --dry-run
```

凭据从环境变量读取：
```bash
$env:JQ_USERNAME="your_username"
$env:JQ_PASSWORD="your_password"
```

> **注意**：不抑制 jqdata warning（用户偏好），warning 有助于发现数据质量问题。

---

## config.yaml 调仓配置汇总

```yaml
rebalance:
  frequency: monthly              # 调仓频率
  method: cost_benefit            # 调仓方法
  cost_benefit_threshold: 0.001   # 成本收益阈值
  cost_model:
    name: stock_cn                # 成本模型
    # 可选费率覆盖：
    # commission_rate: 0.00025
    # stamp_duty: 0.0005
```

### 各策略调仓配置对照

| 策略 | frequency | method | cost_model | threshold |
|------|-----------|--------|------------|-----------|
| ycj/v1 | monthly | cost_benefit | stock_cn | 默认 |
| ycj/v2 | monthly | cost_benefit | stock_cn | 0.001 |
| dh/v1 | quarterly | simple | stock_cn | - |
| etf/v1 | monthly | cost_benefit | etf_cn | 默认 |
| etf/v2 | monthly | cost_benefit | mixed_cn | 0.001 |
| dl/v1 | monthly | cost_benefit | stock_cn | 0.002 |
| rl/v1 | monthly | cost_benefit | stock_cn | 0.002 |
