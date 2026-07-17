# 行业轮动策略 (industry_rotation) 完整报告

> **当前最终版本**: industry_rotation_v5 (mf10_mom60_120_mkt20, final)
> **锁定日期**: 2026-07-16
> **OOS 区间**: 2026-06-01 ~ 2026-07-15 (32 个交易日)
> **版本历史**: 详见第 2.2 节 (v1→v8 共 8 个版本迭代)

---

## 1. 策略概述

### 1.1 核心思路

行业轮动策略：在强势行业中选强势个股，利用聚宽260因子做个股层多因子选股。

- **行业层**: 60+120日动量排名，选Top-5申万一级行业
- **个股层**: 10因子等权z-score复合评分，每行业选Top-2个股
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

3. 个股多因子评分 (10因子等权z-score)
   ├── 动量类: Price1M, Price3M, ROC20
   ├── 成交量类: DAVOL10, money_flow_20
   ├── 质量类: gross_income_ratio, roe_ttm, net_profit_ratio
   └── 价值类: earnings_to_price_ratio, book_to_price_ratio
   └── 每行业选 Top-2 个股

4. 等权配置 + 10%单股上限 + 30%行业上限 + 大盘过滤系数
```

### 1.3 因子数据

- **来源**: jqdata 预计算因子 (factors_wide 视图)
- **使用数量**: 10 个因子 (从260因子中选取)
- **年份覆盖**: 2018-2026
- **存储路径**: `D:/Work/Project/download_a_share/data/parquet/factors_wide/**/*.parquet`

---

## 2. 策略命名规范

### 2.1 命名规则

```
{strategy_type}_{version}  →  超参标签  →  状态标记
industry_rotation _  v5   →  mf10_mom60_120_mkt20  →  final
```

| 组成 | 说明 | 示例 |
|------|------|------|
| `strategy_type` | 行业轮动 | `industry_rotation` = Industry Rotation |
| `version` | 主版本号 | `v1` ~ `v8` |
| 超参标签 | 关键超参 | `mf10` = 10因子, `mom60_120` = 60/120日动量, `mkt20` = 大盘20日过滤 |
| 状态 | 是否已收敛 | `final` = 锁定, `exp` = 实验中 |

### 2.2 版本历史

| 版本 | 超参标签 | IS总收益 | IS Sharpe | IS最大回撤 | 状态 | 关键变更 |
|------|----------|----------|-----------|------------|------|----------|
| industry_rotation_v1 | mom20_60_drawdown | -6.27% | -0.0043 | -23.04% | archived | 日频+drawdown+20/60日动量 |
| industry_rotation_v2 | mom20_60_vol15 | +2.74% | 0.1402 | -30.60% | archived | 周频+vol_target0.15 |
| industry_rotation_v3 | mom60_120_mkt60 | +38.55% | 0.4532 | -24.80% | archived | 周频+大盘60日过滤+60/120日+regime |
| industry_rotation_v4 | mom60_120_mkt20_vol12 | +59.89% | 0.6094 | -23.81% | archived | 大盘10/20日敏感过滤+纯动量 |
| **industry_rotation_v5** | **mf10_mom60_120_mkt20** | **+50.63%** | **0.5766** | **-20.17%** | **final** | **10因子等权多因子选股** |
| industry_rotation_v6 | mf8_momenh_lowvol | +39.99% | 0.4885 | -21.11% | archived | 动量增强+低波因子(负权重) |
| industry_rotation_v7 | ml_lgb252_h20 | +23.92% | 0.4060 | -20.25% | archived | ML选股(LightGBM,原始特征) |
| industry_rotation_v8 | ml_lgb504_zs_h20 | +31.64% | 0.4733 | -23.70% | archived | ML增强(z-score+504天窗口+300树) |

### 2.3 迭代关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 候选池 | 沪深300 | IS Sharpe最优,避免中证800有色金属集中风险 |
| 动量窗口 | 60+120日 | 中长期动量在行业轮动中最稳定 |
| 大盘过滤 | 10/20日均线 | 网格搜索最优,敏感控制回撤 |
| 调仓频率 | 周频 | 日频交易成本过高 |
| 个股选股 | 10因子等权 | 优于纯动量(v4)和ML(v7/v8) |
| 风控 | regime_adaptive | 综合CVaR+regime+drawdown |

---

## 3. 样本内验证 (IS: 2022-2025)

> **方法论**: 所有参数选择均基于 IS 数据 (2022-2025)，OOS (20260601+) 仅做最终验证。

### 3.1 IS 回测结果对比

| 版本 | 总收益 | 年化 | Sharpe | 最大回撤 | 胜率 | 调仓次数 | 方法 |
|------|--------|------|--------|----------|------|----------|------|
| v4 | +59.89% | +12.44% | 0.6094 | -23.81% | 46.49% | 90 | 纯动量(回撤超标) |
| **v5** | **+50.63%** | **+10.77%** | **0.5766** | **-20.17%** | 46.49% | 204 | **10因子等权(最优)** |
| v6 | +39.99% | +8.76% | 0.4885 | -21.11% | 46.38% | 204 | 动量增强+低波(恶化) |
| v7 | +23.92% | +5.50% | 0.4060 | -20.25% | 46.49% | 204 | ML原始特征(恶化) |
| v8 | +31.64% | +7.11% | 0.4733 | -23.70% | 46.49% | 204 | ML z-score+长窗口(恶化) |

### 3.2 关键Bug修复

迭代过程中修复了3个严重bug：

1. **market_filter null值**: 大盘指数早期数据close为null，导致`np.mean()`返回nan，市场过滤完全失效。修复：`.drop_nulls("close")`
2. **日期类型比较**: `pl.col("date").cast(pl.Utf8)`将datetime转为"2024-01-05 00:00:00"，与"2024-01-05"比较错误。修复：改用`pl.col("date").dt.date()`做date类型比较
3. **配置浅合并**: `base_config.update(config)`浅合并导致子dict被整体替换，网格搜索实际在用默认icir选股器。修复：添加`_deep_merge()`递归合并

### 3.3 ML方法探索结论

v7/v8使用LightGBM回归模型预测20日未来收益，均未超过v5的简单等权线性模型：

- **v7** (原始特征, 252天窗口, 150树): +23.92%, Sharpe 0.4060 — 原始因子值有不同量纲，模型学习绝对水平而非相对排名
- **v8** (z-score特征, 504天窗口, 300树): +31.64%, Sharpe 0.4733 — z-score改善了预测但回撤反而增大(-23.70%)

**结论**: 10因子等权线性组合(v5)优于ML非线性模型。原因：因子间非线性关系有限，20日收益标签噪声大，ML易过拟合。

---

## 4. 样本外验证 (OOS: 2026-06-01 ~ 2026-07-15)

### 4.1 OOS 回测结果

| 版本 | OOS总收益 | OOS Sharpe | OOS最大回撤 | OOS胜率 | 调仓次数 |
|------|-----------|------------|-------------|---------|----------|
| v4 | -5.83% | -1.1789 | -17.20% | 48.39% | 7 |
| **v5** | **-3.82%** | **-0.9175** | **-11.31%** | 45.16% | 7 |

### 4.2 OOS 分析

- 两个策略在OOS期间均亏损（市场下行），但v5亏损更小、回撤更可控
- v5的多因子选股提供了更好的下行保护：最大回撤 -11.31% vs v4的 -17.20%
- 大盘趋势过滤生效：总权重70-77%（非满仓），说明大盘均线信号正确降低了仓位
- 行业轮动：6月1日建仓(电子/通信/公用事业/煤炭/建筑材料)，6月22日切换至(电子/通信/建筑材料/有色金属/化工)
- v5持仓与v4不同：v5多因子选股选到不同个股，避免了部分有色崩盘损失

### 4.3 收敛判断

| 条件 | v5是否满足 |
|------|-----------|
| IS Sharpe最优(含回撤达标) | ✓ (0.5766, DD -20.17%) |
| OOS优于基线(v4) | ✓ (收益-3.82% vs -5.83%, DD -11.31% vs -17.20%) |
| ML/手动调权无法改进 | ✓ (v6/v7/v8均恶化) |
| **结论** | **v5收敛，标记为final** |

---

## 5. v5 配置详情

### 5.1 策略参数

```yaml
strategy_type: industry_rotation
strategy_version: v5
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
    factor_names: [10个因子]
    factor_weights: {所有: 1.0}  # 等权

risk:
  method: regime_adaptive
  target_vol: 0.12
  lookback: 20
  min_exposure_scale: 0.3

rebalance:
  frequency: weekly              # 周频
  weekday: 0                     # 周一
  method: cost_benefit
```

### 5.2 因子列表

| 类别 | 因子名 | 方向 |
|------|--------|------|
| 动量 | Price1M | 正(高=好) |
| 动量 | Price3M | 正 |
| 动量 | ROC20 | 正 |
| 成交量 | DAVOL10 | 正 |
| 成交量 | money_flow_20 | 正 |
| 质量 | gross_income_ratio | 正 |
| 质量 | roe_ttm | 正 |
| 质量 | net_profit_ratio | 正 |
| 价值 | earnings_to_price_ratio | 正 |
| 价值 | book_to_price_ratio | 正 |

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
| lightgbm | 4.6.0 | ML选股(v7/v8,可选) |

### 6.2 数据依赖

| 数据 | 来源 | 路径 |
|------|------|------|
| A股日频行情 | download_a_share | `stock_daily_wide_partitioned/` |
| 申万一级行业 | download_a_share | `stock_daily_wide.sw_l1_name` |
| 指数行情 | download_a_share | `parquet/index_daily_price/` |
| 聚宽260因子 | jqdata | `parquet/factors_wide/` |
| 交易日历 | download_a_share | `parquet/trade_calendar/` |

### 6.3 模型依赖

- v5(最终版): 无ML模型，纯多因子线性组合
- v7/v8(已归档): LightGBM Regressor

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
- `parquet/factors_wide/year=YYYY/data.parquet` (聚宽因子)

### 7.3 运行 IS 回测

```bash
python scripts/industry_rotation_is.py v5
```

### 7.4 运行 OOS 回测

```bash
python scripts/industry_rotation_oos.py v5
```

### 7.5 版本对比

```bash
python scripts/industry_rotation_is.py v4 v5     # IS对比
python scripts/industry_rotation_oos.py v4 v5    # OOS对比
```

---

## 8. 建仓/调仓分析

### 8.1 OOS 建仓 (2026-06-01)

- **股票数**: 10只
- **总权重**: 70.00% (大盘过滤降仓)
- **权重范围**: [7.00%, 7.00%] (等权)
- **行业分布**: 电子14%, 通信14%, 公用事业14%, 煤炭14%, 建筑材料14%

### 8.2 OOS 调仓历史

| 日期 | 股票数 | 总权重 | 行业 |
|------|--------|--------|------|
| 2026-06-01 | 10 | 70.00% | 电子/通信/公用事业/煤炭/建筑材料 |
| 2026-06-08 | 10 | 71.30% | 同上 |
| 2026-06-15 | 10 | 70.00% | 同上 |
| 2026-06-22 | 10 | 74.10% | 电子/通信/建筑材料/有色金属/化工 |
| 2026-06-29 | 10 | 76.30% | 同上 |
| 2026-07-06 | 10 | 73.40% | 同上 |
| 2026-07-13 | 10 | 70.00% | 同上 |

### 8.3 换手率

- 6/1→6/8: 0只新增, 0只剔除 (无换手)
- 6/15→6/22: 行业轮动(公用事业/煤炭 → 有色金属/化工), 部分个股更换
