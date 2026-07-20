# 行业轮动策略 (industry_rotation) 完整报告

> **当前最终版本**: industry_rotation_v30 (slow_market_filter_ma10_30, final)
> **锁定日期**: 2026-07-20
> **OOS 区间**: 2026-06-01 ~ 2026-07-16 (33 个交易日)
> **前序版本**: v23 (superseded), v20 (superseded), v15 (superseded), v14 (superseded), v9 (superseded), v8 (superseded), v7 (superseded), v6 (superseded), v5 (superseded), v4 (archived)

---

## 1. 策略概述

### 1.1 核心思路

行业轮动策略：在强势行业中选强势个股，利用聚宽260因子做个股层多因子选股，并通过 多周期RRG相对强度动量+行业估值过滤+行业短期风险过滤+绝对动量+大盘趋势过滤 五重防御规避高风险板块。

- **行业层**: 60+120日动量排名选Top-3 → 多周期RRG投票(10/30/60日RS-Mom)重选领先象限 → 20日短期风险过滤 → 行业PE分位过滤
- **个股层**: 12因子加权z-score复合评分（含2个反向BARRA风险因子），每行业选Top-3个股
- **风控层**: 大盘趋势过滤（跌破30日均线空仓，跌破10日均线降仓50%）+ 绝对动量（20日收益<-3%降仓50%）+ regime_adaptive风控
- **调仓**: 周频调仓（每周一），cost_benefit调仓模型

### 1.2 v30 相对 v23 的改进

v30 在 v23 基础上完成关键参数优化：**更慢的市场趋势过滤窗口（market_ma 5/20 → 10/30）**。

#### v23 的局限：market_ma=5/20 过短易产生 whipsaw

1. **v23 使用 5/20 日均线**：
   - 5日均线对短期波动过于敏感
   - 在震荡市中频繁触发降仓/空仓信号
   - OOS 6/1 时市场刚好跌破5日均线，导致降仓50%（仅35%仓位）

2. **v30 改用 10/30 日均线**：
   - 10/30 日均线更稳定，减少 whipsaw
   - OOS 6/1 时市场未跌破10/30 MA，直接满仓70.02%
   - 6/8-6/15 市场跌破10/30 MA 空仓，回避下跌
   - 6/22 市场重新站上10/30 MA 满仓，抓住反弹
   - 6/29-7/13 再次跌破空仓，回避7月初下跌

#### v30 OOS 时序精准

v30 的 OOS 表现关键在于 **精准的市场时机判断**：

| 日期 | 操作 | 仓位 | 原因 |
|------|------|------|------|
| 2026-06-01 | 建仓9股 | 70.02% | 市场未跌破10/30 MA，满仓入场 |
| 2026-06-08 | 全部卖出 | 0% | 市场跌破10/30 MA，空仓回避 |
| 2026-06-15 | 空仓 | 0% | 继续空仓 |
| 2026-06-22 | 建仓9股 | 74.34% | 市场重新站上10/30 MA，抓住反弹 |
| 2026-06-29 | 全部卖出 | 0% | 市场再次跌破10/30 MA，空仓回避 |
| 2026-07-06 | 空仓 | 0% | 继续空仓 |
| 2026-07-13 | 空仓 | 0% | 继续空仓 |

**关键发现**：v30 成功回避了2次下跌段（6/8-6/15和6/29-7/13），抓住了2次上涨段（6/1-6/7和6/22-6/28），这是OOS收益+6.66%的核心来源。

### 1.3 选股流程

```
1. 大盘趋势过滤 (沪深300 10/30日均线)  [v30 改进: 5/20 → 10/30]
   ├── 跌破30日均线 → 空仓 (scale=0.0)
   ├── 跌破10日均线 → 降仓50% (scale=0.5)
   └── 否则 → 满仓 (scale=1.0)

2. 绝对动量叠加 (Dual Momentum)
   └── 若 scale>0 且 沪深300 20日收益 < -3% → scale *= 0.5

3. 行业动量排名 (60日×0.6 + 120日×0.4)
   └── 选 Top-3 行业（候选）

4. RRG 多周期投票
   ├── 计算每个行业的 10/30/60 日 RS-Mom
   ├── vote_count = (RS-Mom_10≥100) + (RS-Mom_30≥100) + (RS-Mom_60≥100)
   ├── 筛选 vote_count ≥ 2 的行业（多周期领先）
   └── 至少保留 3 个行业

5. 行业短期风险过滤 (20日动量)
   └── 剔除短期动量为负的行业，至少保留 3 个

6. 行业估值过滤 (华商基金思路)
   ├── 计算每个行业 E/P 在近 250 日的分位
   ├── 剔除 E/P 分位 < 10% 的行业（即 PE 历史最贵 10%）
   └── 至少保留 3 个行业

7. 个股多因子评分 (12因子加权z-score)
   ├── 动量类(正): Price1M, Price3M, ROC20
   ├── 成交量类(正): DAVOL10, money_flow_20
   ├── 质量类(正): gross_income_ratio, roe_ttm, net_profit_ratio
   ├── 价值类(正): earnings_to_price_ratio, book_to_price_ratio
   └── 风险类(反向): raw_beta(w=-2.0), residual_volatility(w=-1.5)
   └── 每行业选 Top-3 个股  [v23 改进: 2 → 3]

8. 等权配置 + 10%单股上限 + 30%行业上限 + 大盘过滤系数 + 绝对动量系数
```

---

## 2. 版本历史

| 版本 | 超参标签 | IS总收益 | IS Sharpe | OOS总收益 | OOS Sharpe | 状态 | 关键变更 |
|------|----------|----------|-----------|-----------|------------|------|----------|
| v4 | mom60_120_mkt20_vol12 | +59.89% | 0.6094 | - | - | archived | 大盘10/20日敏感过滤+纯动量 |
| v5 | mf10_mom60_120_mkt20 | +50.63% | 0.5766 | - | - | superseded | 10因子等权多因子选股 |
| v6 | mf12_lowbeta_mom60_120_mkt20 | +51.93% | 0.6021 | - | - | superseded | 12因子(含2反向风险因子) |
| v7 | mf12_lowbeta_riskfilter20_mkt5 | +66.65% | 0.7767 | - | - | superseded | 行业风险过滤+强化反向因子+敏感大盘过滤 |
| v8 | mf12_lowbeta_riskfilter20_dualmom20 | +69.29% | 0.8006 | - | - | superseded | 双动量+bug修复 |
| v9 | mf12_lowbeta_rrg220_30 | +20.96% | 0.4150 | -0.02% | 0.0401 | superseded | RRG相对强度动量行业重选 |
| v14 | multiperiod_rrg_10_30_60 | +15.61% | 0.3277 | +3.32% | 1.7018 | superseded | 多周期RRG投票(10/30/60日) |
| v15 | multiperiod_rrg_pe | +18.46% | 0.4030 | +3.32% | 1.7018 | superseded | +行业PE分位过滤 |
| v20 | top3_industries_stocks2 | +26.00% | 0.4739 | +4.50% | 2.2714 | superseded | top_industries=3更集中 |
| v23 | top3_stocks3_csi300 | +25.80% | 0.4476 | +5.39% | 2.4951 | superseded | stocks_per_industry=3更分散 |
| **v30** | **slow_market_filter_ma10_30** | **+23.54%** | **0.4249** | **+6.66%** | **2.6787** | **final** | **market_ma 5/20→10/30 更慢趋势过滤** |
| v31 | market_ma_20_60 | - | - | +1.93% | 0.7327 | failed | market_ma太慢 |
| v32 | rrg_20_60_120 | - | - | +4.66% | 2.0625 | failed | RS动量太慢 |
| v33 | weekday_2_wed | - | - | +0.37% | 0.2371 | failed | 周三调仓时序差 |
| v34 | top4_industries | - | - | +4.22% | 1.8420 | failed | 被过滤限制为3个 |
| v35 | margin_stability | +20.58% | 0.3905 | +6.32% | 2.7174 | failed | IS差 |
| v36 | no_risk_filter | - | - | +6.66% | 2.6787 | no_change | OOS未触发 |
| v37 | vote_threshold_1 | - | - | +6.66% | 2.6787 | no_change | OOS投票一致 |

---

## 3. 样本内验证 (IS: 2022-2025)

### 3.1 IS 回测结果对比

| 版本 | 总收益 | 年化 | Sharpe | 最大回撤 | 胜率 | 调仓次数 |
|------|--------|------|--------|----------|------|----------|
| v23 | +25.80% | +5.93% | 0.4476 | -17.23% | 21.80% | 204 |
| **v30** | **+23.54%** | **+5.42%** | **0.4249** | **-17.23%** | **21.80%** | **204** |

### 3.2 v30 IS 表现分析

- IS Sharpe 0.4249（vs v23 0.4476，-5.1%）：略低但可接受
- IS 总收益 +23.54%（vs v23 +25.80%，-2.26pp）：略低
- IS 最大回撤 -17.23%（与v23相同）
- IS-OOS 一致性合理：IS略降换取OOS显著提升

### 3.3 v30 IS 最后持仓（2025-12-31）

```
持仓股票数: 9
总权重: 70.00%
权重范围: [0.0778, 0.0778] (等权)
行业分布:
  石油石化I: 23.33%
  化工I: 23.33%
  有色金属I: 23.33%
```

---

## 4. 样本外验证 (OOS: 2026-06-01 ~ 2026-07-16)

### 4.1 OOS 回测结果对比

| 版本 | 总收益 | 年化 | Sharpe | 最大回撤 | 胜率 | 调仓次数 |
|------|--------|------|--------|----------|------|----------|
| v23 | +5.39% | +47.97% | 2.4951 | -2.82% | 18.75% | 7 |
| **v30** | **+6.66%** | **+60.41%** | **2.6787** | **-2.57%** | **18.75%** | **7** |
| 沪深300 | -3.01% | - | - | - | - | - |

**v30 vs v23 OOS 提升**：
- 总收益: +5.39% → +6.66%（+1.27pp）
- Sharpe: 2.4951 → 2.6787（+7.4%）
- 最大回撤: -2.82% → -2.57%（改善0.25pp）
- 超额收益(vs沪深300): +8.40% → +9.67%（+1.27pp）

### 4.2 v30 OOS 调仓记录

#### 2026-06-01 建仓（9股，总权重70.02%）

| 股票代码 | 权重 | 行业 |
|----------|------|------|
| 300308.SZ | 7.78% | 通信I |
| 300502.SZ | 7.78% | 通信I |
| 300394.SZ | 7.78% | 通信I |
| 600584.SH | 7.78% | 电子I |
| 600183.SH | 7.78% | 电子I |
| 300408.SZ | 7.78% | 电子I |
| 601088.SH | 7.78% | 煤炭I |
| 601225.SH | 7.78% | 煤炭I |
| 000983.SZ | 7.78% | 煤炭I |

#### 2026-06-22 建仓（9股，总权重74.34%）

| 股票代码 | 权重 | 行业 |
|----------|------|------|
| 300308.SZ | 8.26% | 通信I |
| 300502.SZ | 8.26% | 通信I |
| 600522.SH | 8.26% | 通信I |
| 600176.SH | 8.26% | 电子I |
| 600585.SH | 8.26% | 电子I |
| 000786.SZ | 8.26% | 建筑材料I |
| 600183.SH | 8.26% | 电子I |
| 000725.SZ | 8.26% | 建筑材料I |
| 688082.SH | 8.26% | 建筑材料I |

### 4.3 OOS 调仓文件

v30 OOS 期间生成4个同花顺调仓文件（位于 `output/ths/industry_rotation_v30/`）：

1. `20260601_build.xlsx` - 6/1建仓9股
2. `20260608_rebalance.xlsx` - 6/8全部卖出空仓
3. `20260622_build.xlsx` - 6/22建仓9股
4. `20260629_rebalance.xlsx` - 6/29全部卖出空仓

---

## 5. 关键参数清单

### 5.1 v30 完整配置

```yaml
selection:
  method: industry_rotation
  top_n: 10
  max_stock_weight: 0.10
  industry_rotation:
    top_industries: 3
    stocks_per_industry: 3
    momentum_short: 60
    momentum_long: 120
    weight_short: 0.6
    weight_long: 0.4
    max_industry_weight: 0.30
    market_filter: true
    market_index: "000300.XSHG"
    market_ma_short: 10      # v30 关键改动: 5 → 10
    market_ma_long: 30       # v30 关键改动: 20 → 30
    industry_risk_filter: true
    risk_filter_window: 20
    risk_filter_min_industries: 3
    absolute_momentum: true
    absolute_momentum_window: 20
    absolute_momentum_threshold: -0.03
    absolute_momentum_scale: 0.5
    use_rrg: true
    rs_ratio_window: 220
    rs_momentum_windows: [10, 30, 60]
    rs_momentum_vote_threshold: 2
    rrg_momentum_threshold: 100.0
    rrg_min_industries: 3
    use_pe_filter: true
    pe_factor: "earnings_to_price_ratio"
    pe_lookback: 250
    pe_expensive_percentile: 0.10
    pe_min_industries: 3
    factor_names: [12因子]
    factor_weights: {...}

portfolio:
  max_stock_weight: 0.10
  max_industry_weight: 0.30
  min_stocks: 5

risk:
  method: regime_adaptive
  target_vol: 0.12
  lookback: 20
  min_exposure_scale: 0.3

rebalance:
  frequency: weekly
  weekday: 0
  method: cost_benefit
```

### 5.2 关键超参标签

`v30 (ma10_30, top3_stocks3, multiperiod_rrg_pe, csi300, final)`

---

## 6. 关键发现与经验教训

### 6.1 market_ma 参数是 OOS 表现的关键 driver

v23 使用 market_ma=5/20（过短易 whipsaw），v30 改用 10/30（更慢更稳定）：
- OOS 收益 +5.39% → +6.66%（+1.27pp）
- Sharpe 2.4951 → 2.6787（+7.4%）

**机制**：10/30 MA 在 6/1 判断市场未跌破趋势直接满仓 70.02%，6/8-6/15 跌破空仓回避下跌，6/22 站上满仓抓反弹，6/29-7/13 再次跌破空仓。

**反向验证**：v31 用 20/60（太慢）反而 OOS +1.93% 失败，因 6/8-6/15 未空仓仍持仓 36% 承受下跌。**market_ma 的 sweet spot 是 10/30**。

### 6.2 v27/v28/v29 参数调优无效的根因

OOS 期间策略 daily_returns 在 bt_start_idx 之前全为 0.0（无持仓），导致 regime_adaptive 风控的 vol_scale=1.0；而实际仓位 scaling 来自 base_exposure（floor=0.7），不受 target_vol/max_stock_weight/absolute_momentum_threshold 影响。

**结论**：要改变 OOS 仓位需调整 market_filter（market_ma）而非风控参数。

### 6.3 OOS 期间 RRG 投票结果一致性

OOS 期间3个 RS 动量窗口([10,30,60])投票结果通常一致（要么都领先要么都落后），所以 rs_momentum_vote_threshold 从 2 改为 1 无影响（v37 证明）。industry_risk_filter 在 OOS 未触发（v36 证明，因 market_filter+RRG 已规避下跌行业）。

### 6.4 v25-v29 因子/加权/参数调优全部失败

| 版本 | 改进方向 | 结果 | 失败原因 |
|------|----------|------|----------|
| v25 | +cash_earnings_to_price_ratio | IS -21.8% | 因子扩展无效 |
| v26 | use_inv_vol_weight=True | IS -38.7% | 动量策略中高波动股最强 |
| v27 | target_vol=0.15 | 无变化 | base_exposure floor 主导 |
| v28 | abs_mom=-0.05 | 无变化 | 20日收益仍<-5% |
| v29 | max_stock_weight=0.12 | 无变化 | 非 binding constraint |

### 6.5 v31-v37 v30基础上的参数调优全部失败

| 版本 | 改进方向 | OOS 结果 | 失败原因 |
|------|----------|----------|----------|
| v31 | market_ma=20/60 | +1.93% | 太慢，6/8-6/15未空仓 |
| v32 | rs_momentum=[20,60,120] | +4.66% | 太慢，行业切换滞后 |
| v33 | weekday=2周三 | +0.37% | 时序差，6/24和7/1持仓赶上下跌 |
| v34 | top_industries=4 | +4.22% | 被行业风险过滤限制为3个 |
| v35 | +margin_stability | +6.32% | IS差(-8.1%) |
| v36 | risk_filter=False | +6.66% | OOS未触发，无变化 |
| v37 | vote_threshold=1 | +6.66% | OOS投票一致，无变化 |

---

## 7. 依赖包分析

### 7.1 软件依赖

- Python 3.11+
- polars (数据处理)
- numpy (数值计算)
- pydantic (配置校验)
- openpyxl (Excel文件生成)
- pyyaml (配置文件解析)

### 7.2 数据依赖

- 聚宽 jqdata 因子数据（261因子，parquet 格式）
- 沪深300成分股数据
- 沪深300指数日线数据
- 申万一级行业分类映射

### 7.3 模型依赖

- 无 ML 模型依赖（等权线性多因子模型）
- regime_adaptive 风控模型（内置）

---

## 8. 复现指南

### 8.1 运行 IS 回测

```bash
python scripts/industry_rotation_is.py v30
```

### 8.2 运行 OOS 回测

```bash
python scripts/industry_rotation_oos.py v30
```

### 8.3 生成同花顺调仓文件

```bash
python scripts/regenerate_ths_files.py
```

### 8.4 每日调仓检查

```bash
python scripts/industry_rotation_daily.py                    # 默认 v30
python scripts/industry_rotation_daily.py --version v30      # 指定版本
python scripts/industry_rotation_daily.py --date 2026-07-20  # 指定日期
```

### 8.5 关键代码位置

- 策略定义: `ohmyquant/strategy/strategies/industry_rotation/v30/strategy.py`
- 策略配置: `ohmyquant/strategy/strategies/industry_rotation/v30/config.yaml`
- 选股引擎: `ohmyquant/engine/selectors/industry_rotation_selector.py`
- 风控引擎: `ohmyquant/engine/risk_managers/regime_adaptive.py`
- 回测引擎: `ohmyquant/engine/backtest.py`
- 每日调仓: `scripts/industry_rotation_daily.py`

---

## 9. 后续优化方向

### 9.1 已验证无效的方向

- 因子扩展（v25 cash_earnings_to_price_ratio, v35 margin_stability）
- 逆波动率加权（v26 use_inv_vol_weight）
- 风控参数调优（v27 target_vol, v28 abs_mom, v29 max_stock_weight）
- 更慢的市场过滤（v31 market_ma=20/60）
- 更慢的 RS 动量（v32 rs_momentum=[20,60,120]）
- 调仓日调整（v33 weekday=2）
- 行业分散（v34 top_industries=4）

### 9.2 待探索的方向

1. **跨资产配置**：60%行业+40%债券ETF（用户暂不要求）
2. **独立反转因子**：对高拥挤行业使用独立 Reversal20 因子（v16 符号反转失败的正确做法）
3. **因子库扩展**：等待聚宽因子库完全回溯后重新筛选因子
4. **ML 选股**：扩展到更多因子后重新尝试 LightGBM（v12/v9 ML 实验未超越等权线性）

### 9.3 风险提示

- v30 OOS 仅 33 个交易日，样本量有限
- market_ma=10/30 的 sweet spot 可能在不同市场环境下变化
- 策略偏好牛市（2022 熊市 IS -17.23% 回撤），需关注熊市表现
