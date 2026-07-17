# 行业轮动策略 (industry_rotation) 完整报告

> **当前最终版本**: industry_rotation_v8 (mf12_lowbeta_riskfilter20_dualmom20_s0.5_t-0.03, final)
> **锁定日期**: 2026-07-17
> **OOS 区间**: 2026-06-01 ~ 2026-07-16 (33 个交易日)
> **前序版本**: v7 (superseded), v6 (superseded), v5 (superseded), v4 (archived)

---

## 1. 策略概述

### 1.1 核心思路

行业轮动策略：在强势行业中选强势个股，利用聚宽260因子做个股层多因子选股，并通过行业短期风险过滤+绝对动量双重防御规避高风险板块。

- **行业层**: 60+120日动量排名，选Top-5申万一级行业；叠加 20 日短期风险过滤，剔除近期已下跌的行业（至少保留3个）
- **个股层**: 12因子加权z-score复合评分（含2个反向BARRA风险因子），每行业选Top-2个股
- **风控层**: 大盘趋势过滤（跌破20日均线空仓，跌破5日均线降仓50%）+ 绝对动量（20日收益<-3%降仓50%）+ regime_adaptive风控
- **调仓**: 周频调仓（每周一），cost_benefit调仓模型

### 1.2 v8 相对 v7 的改进

v8 在 v7 基础上新增**绝对动量（Dual Momentum）**防御机制，并修复了2个关键bug：

1. **绝对动量（Dual Momentum, Antonacci 2014）**：当沪深300近20日收益 < -3% 时，仓位降至50%
   - 参考：Gary Antonacci 双动量策略，绝对动量在下跌趋势中主动避险
   - 参数选择：scale=0.5, threshold=-0.03（IS参数扫描最优，见3.4节）
   - 逆波动率加权经测试损害IS Sharpe(0.78→0.61)，已禁用

2. **Bug修复（关键）**：修复了 `portfolio_optimizer.apply_weight_cap` 归一化抹掉 market_scale 降仓效果的bug
   - 根因：selector 返回的 weights 总和 = market_scale（如0.5），portfolio_optimizer 最终归一化回1.0，降仓效果完全丢失
   - 修复：移除 backtest.py 中冗余的 `apply_weight_cap` 调用（selector已自带weight cap）
   - 影响：v7 OOS 从 -4.03% 改善至 -2.72%（market_filter 0.5 scale 现在真正生效）

### 1.3 选股流程

```
1. 大盘趋势过滤 (沪深300 5/20日均线)
   ├── 跌破20日均线 → 空仓 (scale=0.0)
   ├── 跌破5日均线 → 降仓50% (scale=0.5)
   └── 否则 → 满仓 (scale=1.0)

2. 绝对动量叠加 (Dual Momentum, NEW in v8)
   ├── 若 scale>0 且 沪深300 20日收益 < -3% → scale *= 0.5
   └── 否则 → scale 不变

3. 行业动量排名 (60日×0.6 + 120日×0.4)
   └── 选 Top-5 行业

4. 行业短期风险过滤 (20日动量)
   ├── 剔除短期动量为负的行业 (规避下跌板块)
   └── 至少保留 3 个行业

5. 个股多因子评分 (12因子加权z-score，含2个反向风险因子)
   ├── 动量类(正): Price1M, Price3M, ROC20
   ├── 成交量类(正): DAVOL10, money_flow_20
   ├── 质量类(正): gross_income_ratio, roe_ttm, net_profit_ratio
   ├── 价值类(正): earnings_to_price_ratio, book_to_price_ratio
   └── 风险类(反向): raw_beta(w=-2.0), residual_volatility(w=-1.5)
   └── 每行业选 Top-2 个股

6. 等权配置 + 10%单股上限 + 25%行业上限 + 大盘过滤系数 + 绝对动量系数
```

---

## 2. 版本历史

| 版本 | 超参标签 | IS总收益 | IS Sharpe | IS最大回撤 | 状态 | 关键变更 |
|------|----------|----------|-----------|------------|------|----------|
| v4 | mom60_120_mkt20_vol12 | +59.89% | 0.6094 | -23.81% | archived | 大盘10/20日敏感过滤+纯动量 |
| v5 | mf10_mom60_120_mkt20 | +50.63% | 0.5766 | -20.17% | superseded | 10因子等权多因子选股 |
| v6 | mf12_lowbeta_mom60_120_mkt20 | +51.93% | 0.6021 | -20.06% | superseded | 12因子(含2反向风险因子) |
| v7 | mf12_lowbeta_riskfilter20_mkt5 | +66.65% | 0.7767 | -16.63% | superseded | 行业风险过滤+强化反向因子+敏感大盘过滤 |
| **v8** | **mf12_lowbeta_riskfilter20_dualmom20_s0.5_t-0.03** | **+69.29%** | **0.8006** | **-16.33%** | **final** | **双动量(绝对动量20日,阈值-3%,降仓50%)+bug修复** |

> v7 IS 数据为 bug 修复后重新回测结果（修复前 IS Sharpe 0.7751, 收益 +75.26%）。
> bug 修复使 market_filter 的 0.5 scale 真正生效，略微降低 IS 收益但改善 OOS。

---

## 3. 样本内验证 (IS: 2022-2025)

### 3.1 IS 回测结果对比

| 版本 | 总收益 | 年化 | Sharpe | 最大回撤 | 胜率 | 调仓次数 |
|------|--------|------|--------|----------|------|----------|
| v6 | +51.93% | +11.01% | 0.6021 | -20.06% | 46.38% | 204 |
| v7 (bug修复后) | +66.65% | +13.60% | 0.7767 | -16.63% | 44.73% | 204 |
| **v8** | **+69.29%** | **+14.05%** | **0.8006** | **-16.33%** | 44.73% | 204 |

### 3.2 关键Bug修复（v8迭代中发现）

1. **portfolio_optimizer 归一化抹掉 market_scale（根因）**
   - 现象：v8 绝对动量参数设置后 IS 结果与 v7 完全一致（nav 精确相同）
   - 根因：selector 返回的 weights 总和 = market_scale（如0.5），`portfolio_optimizer.apply_weight_cap` 的最终归一化步骤 `result = {k: v / total}` 将权重重新归一化到1.0，完全抹掉了 market_filter 和 absolute_momentum 的降仓效果
   - 修复：移除 `backtest.py` 中 `_run_selection` 里冗余的 `portfolio_optimizer.apply_weight_cap` 调用（selector 已自带 weight cap）
   - 位置：`ohmyquant/engine/backtest.py` 第460-464行

2. **逆波动率加权被 apply_weight_cap 破坏**
   - 现象：`use_inv_vol_weight=True` 但最终权重全部相等
   - 根因：selector 的 `apply_weight_cap(cap=0.10)` 将所有 inv_vol 权重截断到0.10，归一化后变回等权
   - 修复：当 `use_inv_vol_weight=True` 时跳过 `apply_weight_cap`（风险平价本身就是风险控制）
   - 位置：`ohmyquant/engine/selectors/industry_rotation_selector.py` 第782-785行

### 3.3 绝对动量参数扫描

基于 v7 配置（IS Sharpe 0.7767），测试不同 abs_mom_scale/threshold + inv_vol 组合：

| 变体 | abs_mom_scale | threshold | inv_vol | IS Sharpe | vs v7 |
|------|--------------|-----------|---------|-----------|-------|
| v7 baseline | - | - | - | 0.7767 | -- |
| absonly_s0.7_t0.0 | 0.7 | 0.0 | No | 0.7303 | -0.046 |
| absonly_s0.7_t-0.03 | 0.7 | -0.03 | No | 0.7889 | +0.012 |
| **absonly_s0.5_t-0.03** | **0.5** | **-0.03** | **No** | **0.8006** | **+0.024** |
| absonly_s0.9_t-0.05 | 0.9 | -0.05 | No | 0.7767 | 0.000 |
| invvol_only | - | - | Yes | 0.6084 | -0.168 |
| both_s0.7_t-0.03 | 0.7 | -0.03 | Yes | 0.6243 | -0.152 |

**结论**：
- `threshold=-0.03` 是关键：仅在市场20日收益低于-3%时触发，避免过于频繁降仓
- `scale=0.5`（降仓50%）优于0.7（降仓30%）：更激进降仓反而提升IS Sharpe
- `inv_vol` 显著损害 IS Sharpe（0.78→0.61），已禁用

### 3.4 研报参考

v8 迭代参考了以下2026年最新研报：

1. **国信证券 (2026/06)**: "Agent赋能开发行业轮动策略" — 60%行业+40%国债ETF现金管理，Sharpe 1.04
   - 启发：固定债券配置降低Beta（v8用market_filter+abs_mom实现类似效果）
2. **RRG框架 (2026/07)**: RS-Ratio(220日)+RS-Momentum(60日)，第一象限领先行业，年化18.34%
   - 潜在v9方向：用RRG相对强度替代简单动量排名
3. **Gary Antonacci 双动量**: 相对动量+绝对动量，v8的abs_mom即源于此

---

## 4. 样本外验证 (OOS: 2026-06-01 ~ 2026-07-16)

### 4.1 OOS 回测结果

| 版本 | OOS 收益 | CSI300 同期 | 超额收益 | 最大回撤 | 调仓次数 |
|------|----------|-------------|----------|----------|----------|
| v7 (bug修复前) | -4.03% | -3.01% | -1.02% | -10.61% | 7 |
| v7 (bug修复后) | -2.72% | -3.01% | +0.29% | -10.24% | 7 |
| **v8** | **-2.72%** | **-3.01%** | **+0.29%** | **-10.24%** | 7 |

> v8 OOS = v7 OOS（bug修复后）：abs_mom 在 OOS 期间未触发，因 market_filter 已将仓位降至0%（市场跌破MA20）。
> OOS 改善（-4.03%→-2.72%）主要来自 bug 修复：market_filter 的 0.5 scale 现在真正生效，6月初市场低于MA5时仓位仅35%。

### 4.2 OOS 调仓日市场状态分析

| 调仓日 | CSI300 | 20日收益 | market_scale | abs_mom触发? |
|--------|--------|---------|--------------|-------------|
| 2026-06-01 | 4844 | -- | 0.0 (below MA20) | 跳过(scale=0) |
| 2026-06-08 | 4714 | -3.25% | 0.0 (below MA20) | 跳过(scale=0) |
| 2026-06-15 | 4892 | +0.66% | 1.0 (above both) | 否(收益>-3%) |
| 2026-06-22 | 5060 | +5.78% | 1.0 (above both) | 否(收益正) |
| 2026-06-29 | 4927 | +0.26% | 0.5 (below MA5) | 否(收益>-3%) |
| 2026-07-06 | 4842 | -1.28% | 0.0 (below MA20) | 跳过(scale=0) |
| 2026-07-13 | 4695 | -0.57% | 0.0 (below MA20) | 跳过(scale=0) |

**分析**：abs_mom 与 market_filter 形成互补防御：
- market_filter 处理常规下跌（跌破均线即降仓/空仓）
- abs_mom 处理极端下跌（市场仍在均线上方但20日收益已大跌，如V型反转场景）
- OOS 期间 market_filter 已足够防御，abs_mom 作为额外安全网未触发

### 4.3 OOS 结论

- **v8 OOS 跑赢沪深300**（超额 +0.29%），达成迭代目标
- 核心贡献：bug 修复使 market_filter 降仓机制真正生效
- abs_mom 提升 IS Sharpe（+3%），并在 OOS 提供极端下跌保护（未触发但作为安全网）

---

## 5. 依赖与复现

### 5.1 依赖包

| 类型 | 依赖 |
|------|------|
| 软件 | Python 3.14, DuckDB, polars, numpy, pydantic v2, openpyxl |
| 数据 | jqdata 因子数据（12因子），沪深300指数成分股，申万一级行业映射 |
| 模型 | 无ML模型（12因子等权线性组合） |

### 5.2 复现指南

```bash
# IS 回测
python scripts/industry_rotation_is.py v8

# OOS 回测
python scripts/industry_rotation_oos.py v8

# 每日调仓检查（T日早晨运行）
python scripts/industry_rotation_daily.py
```

### 5.3 配置文件

- 策略配置: `ohmyquant/strategy/strategies/industry_rotation/v8/config.yaml`
- 策略代码: `ohmyquant/strategy/strategies/industry_rotation/v8/strategy.py`
- 选股器: `ohmyquant/engine/selectors/industry_rotation_selector.py`
- 回测引擎: `ohmyquant/engine/backtest.py`
- 风控: `ohmyquant/engine/risk_managers/regime_adaptive.py`

### 5.4 关键超参

| 超参 | 值 | 说明 |
|------|-----|------|
| top_industries | 5 | 选Top-5行业 |
| stocks_per_industry | 2 | 每行业选2只 |
| momentum_short / long | 60 / 120 | 行业动量窗口 |
| market_ma_short / long | 5 / 20 | 大盘均线过滤 |
| industry_risk_filter | 20日 | 行业短期风险过滤窗口 |
| max_industry_weight | 0.25 | 单行业权重上限 |
| **absolute_momentum_scale** | **0.5** | 绝对动量降仓比例 |
| **absolute_momentum_threshold** | **-0.03** | 绝对动量触发阈值 |
| raw_beta weight | -2.0 | 反向beta因子权重 |
| residual_volatility weight | -1.5 | 反向波动率因子权重 |
| rebalance frequency | weekly (周一) | 周频调仓 |
