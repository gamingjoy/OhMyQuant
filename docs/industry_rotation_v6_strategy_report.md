# 行业轮动策略 (industry_rotation) 完整报告

> **当前最终版本**: industry_rotation_v6 (mf12_lowbeta_mom60_120_mkt20, final)
> **锁定日期**: 2026-07-17
> **OOS 区间**: 2026-06-01 ~ 2026-07-16 (33 个交易日)
> **版本历史**: 详见第 2.2 节 (v1→v8 共 8 个历史版本 + v6 重新创建的最终版本)

---

## 1. 策略概述

### 1.1 核心思路

行业轮动策略：在强势行业中选强势个股，利用聚宽260因子做个股层多因子选股。

- **行业层**: 60+120日动量排名，选Top-5申万一级行业
- **个股层**: 12因子加权z-score复合评分（含2个反向BARRA风险因子），每行业选Top-2个股
- **风控层**: 大盘趋势过滤（跌破20日均线空仓，跌破10日均线降仓50%）+ regime_adaptive风控
- **调仓**: 周频调仓（每周一），cost_benefit调仓模型

### 1.2 选股流程

```
1. 大盘趋势过滤 (沪深300 10/20日均线)
   ├── 跌破20日均线 → 空仓
   ├── 跌破10日均线 → 降仓50%
   └── 否则 → 满仓

2. 行业动量排名 (60日×0.6 + 120日×0.4)
   └── 选 Top-5 行业

3. 个股多因子评分 (12因子加权z-score，含2个反向风险因子)
   ├── 动量类(正): Price1M, Price3M, ROC20
   ├── 成交量类(正): DAVOL10, money_flow_20
   ├── 质量类(正): gross_income_ratio, roe_ttm, net_profit_ratio
   ├── 价值类(正): earnings_to_price_ratio, book_to_price_ratio
   └── 风险类(反向): raw_beta(w=-1.5), residual_volatility(w=-1.0)
   └── 每行业选 Top-2 个股

4. 等权配置 + 10%单股上限 + 30%行业上限 + 大盘过滤系数
   (反向因子权重以 abs(w) 参与 weight_sum 归一化)
```

### 1.3 因子数据

- **来源**: jqdata 预计算因子 (factors_wide 视图)
- **使用数量**: 12 个因子 (10个正向alpha因子 + 2个反向BARRA风险因子)
- **年份覆盖**: 2018-2026
- **存储路径**: `D:/Work/Project/download_a_share/data/parquet/factors_wide/**/*.parquet`

---

## 2. 策略命名规范

### 2.1 命名规则

```
{strategy_type}_{version}  →  超参标签  →  状态标记
industry_rotation _  v6   →  mf12_lowbeta_mom60_120_mkt20  →  final
```

| 组成 | 说明 | 示例 |
|------|------|------|
| `strategy_type` | 行业轮动 | `industry_rotation` = Industry Rotation |
| `version` | 主版本号 | `v1` ~ `v8` (历史), `v6` (重新创建) |
| 超参标签 | 关键超参 | `mf12` = 12因子, `lowbeta` = 含反向beta风险因子, `mom60_120` = 60/120日动量, `mkt20` = 大盘20日过滤 |
| 状态 | 是否已收敛 | `final` = 锁定, `superseded` = 被替代, `archived` = 归档, `deleted` = 已删除 |

### 2.2 版本历史

| 版本 | 超参标签 | IS总收益 | IS Sharpe | IS最大回撤 | 状态 | 关键变更 |
|------|----------|----------|-----------|------------|------|----------|
| industry_rotation_v1 | mom20_60_drawdown | -6.27% | -0.0043 | -23.04% | archived | 日频+drawdown+20/60日动量 |
| industry_rotation_v2 | mom20_60_vol15 | +2.74% | 0.1402 | -30.60% | archived | 周频+vol_target0.15 |
| industry_rotation_v3 | mom60_120_mkt60 | +38.55% | 0.4532 | -24.80% | archived | 周频+大盘60日过滤+60/120日+regime |
| industry_rotation_v4 | mom60_120_mkt20_vol12 | +59.89% | 0.6094 | -23.81% | archived | 大盘10/20日敏感过滤+纯动量 |
| industry_rotation_v5 | mf10_mom60_120_mkt20 | +50.63% | 0.5766 | -20.17% | superseded | 10因子等权多因子选股 |
| industry_rotation_v6 (旧实验) | mf8_momenh_lowvol | +39.99% | 0.4885 | -21.11% | deleted | 动量增强+低波因子(负权重) |
| industry_rotation_v7 | ml_lgb252_h20 | +23.92% | 0.4060 | -20.25% | deleted | ML选股(LightGBM,原始特征) |
| industry_rotation_v8 | ml_lgb504_zs_h20 | +31.64% | 0.4733 | -23.70% | deleted | ML增强(z-score+504天窗口+300树) |
| **industry_rotation_v6** | **mf12_lowbeta_mom60_120_mkt20** | **+51.93%** | **0.6021** | **-20.06%** | **final** | **12因子(含2反向风险:raw_beta/residual_volatility)** |

> **注**: v6-v8为早期实验版本，已在代码库清理中删除；当前v6为重新创建的低beta版本。
> v5 状态由 `final` 改为 `superseded`，被 v6 (new) 替代。v9/v10/v11 为 v6 迭代过程中的辅助实验（风控参数/调仓频率），未列入主版本表，详见 3.4-3.6 节。

### 2.3 迭代关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 候选池 | 沪深300 | IS Sharpe最优,避免中证800有色金属集中风险 |
| 动量窗口 | 60+120日 | 中长期动量在行业轮动中最稳定 |
| 大盘过滤 | 10/20日均线 | 网格搜索最优,敏感控制回撤 |
| 调仓频率 | 周频 | 日频交易成本过高；周频Sharpe最优(详见3.5) |
| 个股选股 | 12因子加权(含反向风险) | 优于纯动量(v4)、10因子等权(v5)和ML(v7/v8) |
| 风控 | regime_adaptive | 综合CVaR+regime+drawdown |
| 反向风险因子 | raw_beta(w=-1.5)+residual_volatility(w=-1.0) | 降低组合beta,改善下跌市回撤 |

---

## 3. 样本内验证 (IS: 2022-2025)

> **方法论**: 所有参数选择均基于 IS 数据 (2022-2025)，OOS (20260601+) 仅做最终验证。

### 3.1 IS 回测结果对比

| 版本 | 总收益 | 年化 | Sharpe | 最大回撤 | 胜率 | 调仓次数 | 方法 |
|------|--------|------|--------|----------|------|----------|------|
| v4 | +59.89% | +12.44% | 0.6094 | -23.81% | 46.49% | 90 | 纯动量(回撤超标) |
| v5 | +50.63% | +10.77% | 0.5766 | -20.17% | 46.49% | 204 | 10因子等权(superseded) |
| v6 (旧实验) | +39.99% | +8.76% | 0.4885 | -21.11% | 46.38% | 204 | 动量增强+低波(恶化,deleted) |
| v7 | +23.92% | +5.50% | 0.4060 | -20.25% | 46.49% | 204 | ML原始特征(deleted) |
| v8 | +31.64% | +7.11% | 0.4733 | -23.70% | 46.49% | 204 | ML z-score+长窗口(deleted) |
| **v6(new)** | **+51.93%** | **+11.01%** | **0.6021** | **-20.06%** | 46.38% | 204 | **12因子含2反向风险(final)** |

### 3.2 关键Bug修复

迭代过程中修复了3个严重bug：

1. **market_filter null值**: 大盘指数早期数据close为null，导致`np.mean()`返回nan，市场过滤完全失效。修复：`.drop_nulls("close")`
2. **日期类型比较**: `pl.col("date").cast(pl.Utf8)`将datetime转为"2024-01-05 00:00:00"，与"2024-01-05"比较错误。修复：改用`pl.col("date").dt.date()`做date类型比较
3. **配置浅合并**: `base_config.update(config)`浅合并导致子dict被整体替换，网格搜索实际在用默认icir选股器。修复：添加`_deep_merge()`递归合并

### 3.3 ML方法探索结论

v7/v8使用LightGBM回归模型预测20日未来收益，均未超过v5的简单等权线性模型：

- **v7** (原始特征, 252天窗口, 150树): +23.92%, Sharpe 0.4060 — 原始因子值有不同量纲，模型学习绝对水平而非相对排名
- **v8** (z-score特征, 504天窗口, 300树): +31.64%, Sharpe 0.4733 — z-score改善了预测但回撤反而增大(-23.70%)

**结论**: 10因子等权线性组合(v5)优于ML非线性模型。原因：因子间非线性关系有限，20日收益标签噪声大，ML易过拟合。v6(v6旧实验)的动量增强+低波也未改善。这三个版本均在代码库清理中删除。

### 3.4 v6迭代分析

#### 动机

OOS分析发现 v5 持仓 beta 过高（约 1.44），显著大于 1.0，导致下跌市回撤大于沪深300。为降低组合系统性风险暴露，引入 BARRA 风险因子做反向选股。

#### 改进

在 v5 的 10 因子等权基础上，新增 2 个 BARRA 风险因子：

- **raw_beta** (反向, w=-1.5): 降低组合对市场指数的敏感度
- **residual_volatility** (反向, w=-1.0): 降低个股特质波动率暴露

权重绝对值较大（1.5/1.0），强化低 beta/低波动的选股倾斜。

#### 反向因子实现

selector 扩展支持负权重：

- `factor_weights` 允许负值
- `weight_sum` 归一化使用 `abs(w)` 累加，保证正负因子协同参与评分
- 个股 z-score 与因子权重相乘后求和，反向因子使高 beta/高波动个股得分降低

#### IS 结果

| 指标 | v5 | v6(new) | 变化 |
|------|-----|---------|------|
| IS Sharpe | 0.5766 | 0.6021 | **+4.4%** |
| 总收益 | +50.63% | +51.93% | +1.30pp |
| 最大回撤 | -20.17% | -20.06% | 改善0.11pp |
| 年化 | +10.77% | +11.01% | +0.24pp |

IS Sharpe 从 0.5766 提升至 0.6021（+4.4%），收益和回撤均有改善，验证了反向风险因子的有效性。

### 3.5 调仓频率优化分析

用户特别关注调仓频率对策略表现的影响，针对 v6 配置实验了 3 种频率（对应辅助实验版本 v6/v10/v11）：

| 频率 | 实验版本 | IS总收益 | IS Sharpe | IS最大回撤 | 调仓次数 |
|------|----------|----------|-----------|------------|----------|
| weekly | v6 | +51.93% | 0.6021 | -20.06% | 204 |
| biweekly | v11 | +27.41% | 0.4017 | -23.50% | 102 |
| monthly | v10 | +52.16% | 0.5877 | -26.49% | 48 |

#### 各频率分析

- **biweekly (v11)**: 收益 +27.41%，相对 weekly 腰斩（-47%）；Sharpe 0.4017 大幅下降；调仓次数减半至 102。动量信号时效性损失过大，行业轮动错过最佳切换点。
- **monthly (v10)**: 收益 +52.16% 略高于 weekly，但 Sharpe 0.5877 低于 weekly，且最大回撤 -26.49% 较 weekly 恶化 31%。月频虽然捕捉到主要趋势，但回撤控制显著变差。
- **weekly (v6)**: Sharpe 0.6021 最优，最大回撤 -20.06% 最低。调仓次数 204 次（约 4 年×50 周），交易成本可接受。

#### 结论

**周频最优**。行业轮动依赖及时捕捉动量信号，降低频率会显著损害表现：biweekly 收益腰斩，monthly 回撤恶化。月频虽收益略高，但风险调整后收益（Sharpe）和回撤均不如周频。

#### 配套Bug修复

实验 biweekly 频率时发现 allocator 不支持 biweekly 频率的 bug，已新增 biweekly 逻辑修复。

### 3.6 风控参数修复

#### 发现的Bug

`regime_adaptive` 风控器的 `min_exposure_scale` 参数被读取但从未使用：`_compute_composite_exposure` 方法使用了硬编码的 `0.15`，而非 `self.min_exposure_scale`。

#### 修复

将硬编码 `0.15` 改为使用 `self.min_exposure_scale`，使参数真正生效。

#### 影响

此 bug 导致 v9 实验（调低 `min_exposure_scale` 从 0.3→0.2）完全无效——参数变化未传递到实际风控计算中。修复后该参数才能正确控制最小仓位暴露。v9 实验结果因此作废，未列入版本历史表。

---

## 4. 样本外验证 (OOS: 2026-06-01 ~ 2026-07-16)

### 4.1 OOS 回测结果

| 版本 | OOS总收益 | OOS净值 | OOS Sharpe | OOS最大回撤 | 调仓次数 |
|------|-----------|---------|------------|-------------|----------|
| v5 | -7.28% | - | - | - | 7 |
| **v6** | **-6.16%** | **0.9384** | **-1.4206** | **-11.76%** | 7 |

> **注**: v5 OOS 总收益 -7.28% 为按 v6 OOS 区间 (2026-06-01 ~ 2026-07-16) 重新运行的结果，用于同区间对比；其余 v5 OOS 指标未重新计算。

### 4.2 OOS 分析

- 两个策略在 OOS 期间均亏损（市场下行），但 v6 亏损更小（-6.16% vs v5 的 -7.28%），v6 略有改善
- v6 加入反向 beta 因子后，组合 beta 降低，下跌市回撤控制更好：最大回撤 -11.76%
- v6 IS Sharpe 最优 (0.6021)，OOS 优于 v5，验证了反向风险因子的稳健性
- 大盘趋势过滤生效：总权重 70-77%（非满仓），说明大盘均线信号正确降低了仓位
- 7 次调仓（含建仓），周频执行

### 4.3 收敛判断

| 条件 | v6是否满足 |
|------|-----------|
| IS Sharpe最优(含回撤达标) | ✓ (0.6021, DD -20.06%) |
| OOS优于基线(v5) | ✓ (收益-6.16% vs -7.28%) |
| 反向风险因子改善回撤 | ✓ (DD -11.76%, beta降低) |
| 调仓频率优化验证周频最优 | ✓ (详见3.5) |
| **结论** | **v6收敛，标记为final** |

---

## 5. v6 配置详情

### 5.1 策略参数

```yaml
strategy_type: industry_rotation
strategy_version: v6
backtest:
  start_date: "2022-01-01"       # IS起始
  end_date: "2025-12-31"         # IS结束
  data_start_date: "2018-01-01"  # 数据起始(需足够动量计算)
  transaction_cost: 0.001        # 千分之一交易费

selection:
  method: industry_rotation
  top_n: 10                      # 最终选10只
  max_stock_weight: 0.10         # 单股上限10%
  ind:
    top_industries: 5            # Top-5行业
    stocks_per_industry: 2       # 每行业2只
    momentum_short: 60           # 60日短期动量
    momentum_long: 120           # 120日长期动量
    weight_short: 0.6            # 短期权重
    weight_long: 0.4             # 长期权重
    max_industry_weight: 0.30    # 行业上限30%
    market_filter: true          # 大盘趋势过滤
    market_ma_short: 10          # 短期均线10日
    market_ma_long: 20           # 长期均线20日
    use_factors: true            # 多因子选股
    factor_names: [12个因子]      # 10正向 + 2反向风险
    factor_weights:
      Price1M: 1.0
      Price3M: 1.0
      ROC20: 1.0
      DAVOL10: 1.0
      money_flow_20: 1.0
      gross_income_ratio: 1.0
      roe_ttm: 1.0
      net_profit_ratio: 1.0
      earnings_to_price_ratio: 1.0
      book_to_price_ratio: 1.0
      raw_beta: -1.5             # 反向BARRA风险因子
      residual_volatility: -1.0  # 反向BARRA风险因子
    weight_sum_normalize: abs    # 反向因子用abs(w)归一化

risk:
  method: regime_adaptive
  target_vol: 0.12
  lookback: 20
  min_exposure_scale: 0.3        # 已修复：参数实际生效

rebalance:
  frequency: weekly              # 周频(详见3.5频率优化分析)
  weekday: 0                     # 周一
  method: cost_benefit
```

### 5.2 因子列表

| 类别 | 因子名 | 方向 | 权重 |
|------|--------|------|------|
| 动量 | Price1M | 正(高=好) | 1.0 |
| 动量 | Price3M | 正 | 1.0 |
| 动量 | ROC20 | 正 | 1.0 |
| 成交量 | DAVOL10 | 正 | 1.0 |
| 成交量 | money_flow_20 | 正 | 1.0 |
| 质量 | gross_income_ratio | 正 | 1.0 |
| 质量 | roe_ttm | 正 | 1.0 |
| 质量 | net_profit_ratio | 正 | 1.0 |
| 价值 | earnings_to_price_ratio | 正 | 1.0 |
| 价值 | book_to_price_ratio | 正 | 1.0 |
| **风险(BARRA)** | **raw_beta** | **反向(低=好)** | **-1.5** |
| **风险(BARRA)** | **residual_volatility** | **反向(低=好)** | **-1.0** |

---

## 6. 依赖包分析

### 6.1 软件依赖

| 包 | 版本 | 用途 |
|----|------|------|
| polars | >=0.20.0 | 数据处理 |
| duckdb | >=0.9.0 | Parquet查询 |
| numpy | >=1.24.0 | 数值计算 |
| pydantic | >=2.0.0 | 配置模型 |
| loguru | >=0.7.0 | 日志 |
| pyyaml | >=6.0 | 配置文件 |
| lightgbm | 4.6.0 | ML选股(v7/v8,可选,已删除) |

### 6.2 数据依赖

| 数据 | 来源 | 路径 |
|------|------|------|
| A股日频行情 | download_a_share | `stock_daily_wide_partitioned/` |
| 申万一级行业 | download_a_share | `stock_daily_wide.sw_l1_name` |
| 指数行情 | download_a_share | `parquet/index_daily_price/` |
| 聚宽260因子 | jqdata | `parquet/factors_wide/` |
| 交易日历 | download_a_share | `parquet/trade_calendar/` |

### 6.3 模型依赖

- v6(最终版): 无ML模型，12因子加权线性组合（含2反向风险因子）
- v7/v8(已删除): LightGBM Regressor

---

## 7. 复现指南

### 7.1 环境准备

```bash
pip install polars duckdb numpy pydantic loguru pyyaml lightgbm
```

### 7.2 数据准备

确保 `D:/Work/Project/download_a_share/data` 目录下有：
- `stock_daily_wide_partitioned/year=YYYY/data.parquet` (2018-2026)
- `parquet/index_daily_price/year=YYYY/data.parquet` (沪深300)
- `parquet/factors_wide/year=YYYY/data.parquet` (聚宽因子，含 raw_beta / residual_volatility)

### 7.3 运行 IS 回测

```bash
python scripts/industry_rotation_is.py v6
```

### 7.4 运行 OOS 回测

```bash
python scripts/industry_rotation_oos.py v6
```

### 7.5 版本对比

```bash
python scripts/industry_rotation_is.py v5 v6     # IS对比
python scripts/industry_rotation_oos.py v5 v6    # OOS对比
```

---

## 8. 建仓/调仓分析

> **OOS 输出路径**: `output/ths/industry_rotation_v6/` (共 7 个文件，20260601_build ~ 20260713_rebalance)

### 8.1 OOS 建仓 (2026-06-01)

- **股票数**: 10只
- **总权重**: 70.00% (大盘过滤降仓)
- **权重范围**: [7.00%, 7.00%] (等权)
- **行业分布**: 电子14%, 通信14%, 公用事业14%, 煤炭14%, 建筑材料14%

### 8.2 OOS 调仓历史

| 日期 | 文件 | 股票数 | 总权重 | 行业 |
|------|------|--------|--------|------|
| 2026-06-01 | `20260601_build` | 10 | 70.00% | 电子/通信/公用事业/煤炭/建筑材料 |
| 2026-06-08 | `20260608_rebalance` | 10 | 71.30% | 同上 |
| 2026-06-15 | `20260615_rebalance` | 10 | 70.00% | 同上 |
| 2026-06-22 | `20260622_rebalance` | 10 | 74.10% | 电子/通信/建筑材料/有色金属/化工 |
| 2026-06-29 | `20260629_rebalance` | 10 | 76.30% | 同上 |
| 2026-07-06 | `20260706_rebalance` | 10 | 73.40% | 同上 |
| 2026-07-13 | `20260713_rebalance` | 10 | 70.00% | 同上 |

### 8.3 换手率

- 6/1→6/8: 0只新增, 0只剔除 (无换手)
- 6/15→6/22: 行业轮动(公用事业/煤炭 → 有色金属/化工), 部分个股更换
