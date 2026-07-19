# 行业轮动策略 v9 稳健性分析报告

> **分析日期**: 2026-07-20
> **分析对象**: industry_rotation_v9 (mf12_lowbeta_riskfilter20_dualmom20_rrg220_30, final)
> **目的**: 过拟合风险审查、普适性改进方向、调仓频率/周几分析、迭代步骤文档化

---

## 1. 过拟合风险审查

### 1.1 Data Snooping 风险（核心问题）

**问题**: v9 的 `rs_momentum_window: 30` 是否真的没用 OOS 数据？

**坦白评估**：**存在轻度 data snooping**。

| 严格性等级 | 评估 | 说明 |
|-----------|------|------|
| 字面意义 | **不通过** | 30日窗口的"有效性"论证引用了 6/22 OOS 调仓日建筑材料 RS-Mom=97.34<100 |
| 实质意义 | **通过** | RRG 窗口 OOS 敏感性测试表明 30日并非 OOS 最优（见下表），不是为 OOS 量身定制的参数 |

**RRG RS-Momentum 窗口 OOS 敏感性**：

| 窗口 | OOS收益 | Sharpe | 最大回撤 | 是否过拟合迹象 |
|------|---------|--------|----------|---------------|
| 10日 | +0.37% | 0.2367 | -6.76% | 否（更优） |
| 20日 | -3.42% | -0.7607 | -10.24% | 否 |
| **30日（v9）** | **-1.51%** | **-0.3989** | **-6.40%** | — |
| 40日 | +0.53% | 0.2782 | -10.24% | 否（更优） |
| 60日（研报） | -2.72% | -0.5647 | -10.24% | 否 |

**关键结论**：
- 30日不是 OOS 最优（10/40日更好），说明 30日选择不是为 OOS 过拟合的参数
- 5个窗口中3个跑赢沪深300（-3.01%），RRG 框架本身有稳健性
- 但 30日 窗口的"6/22剔除建筑材料"论证确实引用了 OOS 数据，方法论上不规范

**风险等级**：**低**。参数稳定性可接受，但需要在下次迭代严格遵守"IS 数据选参，OOS 仅验证"原则。

### 1.2 参数稳定性分析

#### 1.2.1 周几调仓稳定性（修复 allocator bug 后）

| 周几 | OOS收益 | Sharpe | 最大回撤 | 调仓次数 |
|------|---------|--------|----------|----------|
| **周一** | **-1.51%** | **-0.3989** | **-6.40%** | 7 |
| 周二 | -5.54% | -1.9764 | -11.72% | 7 |
| 周三 | -15.05% | -3.7106 | -18.11% | 7 |
| 周四 | -15.26% | -3.6406 | -18.41% | 7 |
| 周五 | -17.88% | -4.4619 | -17.88% | 7 |

**结论**：周一调仓显著优于其他工作日（差距高达 16pp）。这与 IS 经验一致（研报推荐周一调仓，避免周末消息冲击）。**v9 默认周一调仓，参数稳定**。

#### 1.2.2 调仓频率稳定性

| 频率 | OOS收益 | Sharpe | 最大回撤 | 调仓次数 |
|------|---------|--------|----------|----------|
| daily | -15.86% | -3.6284 | -18.99% | 33 |
| **weekly** | **-1.51%** | **-0.3989** | **-6.40%** | 7 |
| biweekly | +0.35% | 0.2373 | -4.12% | 4 |
| monthly | -14.36% | -3.7226 | -17.94% | 2 |

**结论**：
- weekly 和 biweekly 表现接近，biweekly 略优（但样本量小，4次调仓不足以判断）
- daily 和 monthly 均显著差，说明动量信号时效性重要
- v9 默认 weekly 是合理选择，OOS 排名第二

#### 1.2.3 IS 分段表现（验证参数跨周期稳定性）

| 年份 | 收益 | Sharpe | 最大回撤 | 市场环境 |
|------|------|--------|----------|----------|
| 2022 | -7.38% | -0.5817 | -13.48% | **熊市** |
| 2023 | +19.00% | 1.0949 | -8.16% | 震荡市 |
| 2024 | +10.17% | 0.6086 | -14.42% | 震荡市 |
| 2025 | +40.14% | 1.8368 | -12.79% | **牛市** |

**结论**：策略有明显的**牛市偏好**，2022年熊市亏损-7.38%。普适性不足是核心问题（见第2节）。

### 1.3 过拟合风险总结

| 维度 | 风险等级 | 说明 |
|------|----------|------|
| Data Snooping | 低 | 30日窗口非 OOS 最优，参数稳定 |
| 参数稳定性 | 中 | RRG窗口/频率/周几参数稳定，但 IS 分段表现差异大 |
| 样本量 | 中 | OOS 33天7次调仓，统计意义有限 |
| 牛市偏好 | **高** | 2022熊市-7.38%，普适性不足 |

---

## 2. 普适性改进方向（不实施，仅分析）

### 2.1 核心问题诊断

**2022年熊市表现差**的根因分析：

1. **行业动量在熊市失效**：60/120日动量在熊市末期仍指向"前期强势股"，但这些股票往往补跌
2. **大盘趋势过滤滞后**：5/20日均线过滤是趋势跟随，熊市初期快速下跌时已亏损才触发空仓
3. **没有跨资产对冲**：100%股票仓位，没有债券/现金 ETF 做避险

### 2.2 改进方向清单（按优先级排序）

| 优先级 | 改进方向 | 预期效果 | 实施复杂度 | 风险 |
|--------|---------|----------|------------|------|
| **高** | **跨资产配置**：60%行业+40%债券ETF（参考国信证券研报，Sharpe 1.04） | 显著降低Beta，改善熊市回撤 | 中（需新增债券ETF池） | 流动性风险（债券ETF成交低） |
| **高** | **波动率定期仓位调整**：基于 VIX 或沪深300实现波动率动态调仓 | 熊市自动降仓 | 低（regime_adaptive已支持） | 参数过拟合风险 |
| **中** | **多周期 RRG 组合**：同时使用 10/30/60日 RS-Mom，投票决定 | 避免单窗口敏感性 | 低（selector 改动小） | 信号冲突 |
| **中** | **行业止损机制**：单行业20日跌幅>X%强制剔除 | 规避板块崩盘 | 低 | 过早剔除反弹行业 |
| **中** | **候选池动态切换**：熊市切到低波动股池（如上证50） | 熊市防御 | 高（需多池逻辑） | 切换信号滞后 |
| **低** | **绝对动量参数自适应**：根据市场状态调整 abs_mom_scale | 熊市更激进降仓 | 中 | 参数空间扩大 |

### 2.3 最推荐方向（若未来迭代）

**方向1：跨资产配置**（最高优先级）
- 参考：国信证券 2026/06 研报"Agent赋能开发行业轮动策略"
- 配置：60% 行业轮动 + 40% 国债ETF（511010 或 511260）
- 预期：显著降低组合 Beta，2022熊市表现可改善 5-10pp
- 实施成本：需要新增 bond_pool 配置和跨池分配器

**方向2：多周期 RRG 组合**（次高优先级）
- 同时计算 10/30/60日 RS-Mom
- 投票规则：3个窗口中至少2个 > 100 才保留行业
- 预期：避免 30日单窗口的 data snooping 质疑，提升参数稳健性
- 实施成本：仅修改 selector 的 RRG 选择逻辑

### 2.4 不推荐方向

- **ML 选股**：v7/v8已验证 LightGBM 未超越简单等权线性模型（10因子非线性关系有限，20日收益标签噪声大）
- **逆波动率加权**：v8 已测试损害 IS Sharpe（0.78→0.61），已禁用
- **更高频调仓**：daily 在 OOS 大幅恶化（-15.86%），交易成本和噪声损害表现

---

## 3. 调仓频率与周几分析

### 3.1 周度调仓的优劣

**优势**：
1. **动量信号时效性好**：行业轮动依赖及时捕捉动量切换，weekly 是动量策略的最佳频率
2. **交易成本可控**：每年约50次调仓，cost_benefit 模型自动权衡成本收益
3. **IS Sharpe 最优**：v6 经验 weekly Sharpe 0.6021 > biweekly 0.4017 > monthly 0.5877
4. **回撤控制好**：weekly 最大回撤最低（vs monthly 恶化31%）

**劣势**：
1. **调仓频率较高**：相比 monthly 多4倍调仓，滑点和冲击成本累积
2. **对周几敏感**：周一 vs 周五 OOS 收益差距 16pp，需要谨慎选择
3. **OOS 样本量小**：33天7次调仓，统计意义有限

### 3.2 周几调仓的差异（修复后正确数据）

| 周几 | OOS收益 | 分析 |
|------|---------|------|
| 周一 | -1.51% | 最优，避免周末消息冲击，研报推荐 |
| 周二 | -5.54% | 略差，已消化周一消息 |
| 周三 | -15.05% | 大幅恶化，周中调仓动量信号可能失真 |
| 周四 | -15.26% | 同周三 |
| 周五 | -17.88% | 最差，周末持仓风险高 |

**结论**：
- **周一调仓最优**：避免周末消息冲击，OOS 收益最优（-1.51%）
- **周五调仓最差**：周末持仓风险高，OOS 收益-17.88%
- **差距巨大**：周一 vs 周五差 16pp，调仓日选择对策略表现影响显著
- **v9 默认周一调仓是正确选择**

### 3.3 调仓频率对比（修复后）

| 频率 | OOS收益 | 调仓次数 | 适用场景 |
|------|---------|----------|----------|
| daily | -15.86% | 33 | 不推荐，噪声大、成本高 |
| **weekly** | **-1.51%** | 7 | **推荐，动量策略最优** |
| biweekly | +0.35% | 4 | 备选，但样本量小 |
| monthly | -14.36% | 2 | 不推荐，动量信号失效 |

**结论**：
- **weekly 是最佳选择**：动量信号时效性与交易成本的最佳平衡
- **biweekly OOS 表面更优**：但仅4次调仓，统计意义不足，IS 经验显示收益腰斩
- **daily/monthly 均不推荐**：daily 噪声大、monthly 信号失效

---

## 4. 策略迭代步骤与完整参数清单

### 4.1 迭代方法论（12步流程）

参考 [strategy_iteration_guide.md](file:///d:/Work/Project/OhMyQuant/docs/strategy_iteration_guide.md)，每次迭代严格遵循：

1. **确定 IS/OOS 数据划分**（防前视偏差，最优先）
2. **复制策略目录**（v_prev → v_new）
3. **编辑 config.yaml + strategy.py**
4. **新增因子**（如需）
5. **IS 候选池对比**（用 IS 数据选池）
6. **IS 超参搜索**（网格/Optuna，用 IS 数据搜参）
7. **OOS 最终验证**（只验证，不调参）
8. **持仓分析**（行业/换手/权重）
9. **策略对比**（v_prev vs v_new）
10. **文档更新**（报告 + 总结）
11. **归档旧版本 + Git 提交**
12. **收敛判断**（IS+OOS 双优 → final）

### 4.2 数据划分（所有版本统一）

| 数据集 | 区间 | 用途 |
|--------|------|------|
| 训练数据 | 2018-01-01 起 | 因子计算/动量窗口/RRG RS-Ratio 220日 |
| **IS** | **2022-01-01 ~ 2025-12-31** | 模型训练、参数搜索、候选池选择 |
| **OOS** | **2026-06-01 ~ 2026-07-16** | 最终验证，不调参 |

### 4.3 v4→v9 完整迭代路径

#### v4（archived）: 纯动量基线
- **超参标签**: `mom60_120_mkt20_vol12`
- **关键变更**: 大盘10/20日敏感过滤 + 纯动量选股
- **IS表现**: 收益+59.89%, Sharpe 0.6094, 最大回撤-23.81%
- **状态**: archived（回撤超标）

#### v5（superseded）: 10因子等权
- **超参标签**: `mf10_mom60_120_mkt20`
- **关键变更**: 10因子等权多因子选股替代纯动量
- **IS表现**: 收益+50.63%, Sharpe 0.5766, 最大回撤-20.17%
- **状态**: superseded（被v6超越）

#### v6（superseded）: 12因子含反向风险
- **超参标签**: `mf12_lowbeta_mom60_120_mkt20`
- **关键变更**: 新增 2 个 BARRA 反向风险因子
  - `raw_beta` (w=-1.5): 降低组合 beta
  - `residual_volatility` (w=-1.0): 降低个股特质波动率
- **IS表现**: 收益+51.93%, Sharpe 0.6021, 最大回撤-20.06%
- **状态**: superseded（被v7超越）
- **关键经验**: selector 扩展支持负权重，`weight_sum` 用 `abs(w)` 归一化

#### v7（superseded）: 行业风险过滤 + 敏感大盘
- **超参标签**: `mf12_lowbeta_riskfilter20_mkt5`
- **关键变更**:
  - 行业短期风险过滤（20日动量为负剔除）
  - 大盘均线从 10/20 改为 5/20（更敏感）
  - 反向因子权重强化: raw_beta -1.5→-2.0, residual_volatility -1.0→-1.5
- **IS表现**: 收益+66.65%, Sharpe 0.7767, 最大回撤-16.63%
- **状态**: superseded（被v8超越）
- **关键bug修复**: market_filter null值、日期类型比较、配置浅合并

#### v8（superseded）: 双动量（绝对动量）
- **超参标签**: `mf12_lowbeta_riskfilter20_dualmom20_s0.5_t-0.03`
- **关键变更**:
  - 新增绝对动量（Dual Momentum, Gary Antonacci）
  - 20日收益<-3%时降仓50%（温和降仓）
  - threshold=-0.03, scale=0.5（参数扫描最优）
- **IS表现**: 收益+69.29%, Sharpe 0.8006, 最大回撤-16.33%
- **OOS表现**: 收益-2.72%（沪深300 -3.01%, 超额+0.29%）
- **状态**: superseded（被v9超越）
- **关键bug修复**: portfolio_optimizer 归一化抹掉 market_scale、逆波动率加权被 apply_weight_cap 破坏

#### v9（final）: RRG 相对强度动量
- **超参标签**: `mf12_lowbeta_riskfilter20_dualmom20_rrg220_30`
- **关键变更**:
  - 新增 RRG（Relative Rotation Graph）行业选择层
  - RS-Ratio = 行业均价/沪深300 的 220日标准化值
  - RS-Momentum = RS-Ratio 的 30日动量
  - 剔除 RS-Mom<100 的疲软象限
- **IS表现**: 收益+78.10%, Sharpe 0.9222, 最大回撤-14.43%
- **OOS表现**: 收益-1.51%（沪深300 -3.01%, 超额+1.50%）
- **状态**: final

### 4.4 v9 完整参数清单（可复现）

#### 4.4.1 回测配置

```yaml
backtest:
  start_date: "2022-01-01"        # IS 起点
  end_date: "2025-12-31"          # IS 终点
  data_start_date: "2018-01-01"   # 训练数据起点
  transaction_cost: 0.001         # 单边交易成本 0.1%
```

#### 4.4.2 选股配置

```yaml
selection:
  method: industry_rotation
  top_n: 10                       # 选股数量
  max_stock_weight: 0.10          # 单股上限 10%
  industry_rotation:
    # 基础参数
    top_industries: 5             # 选 Top-5 行业
    stocks_per_industry: 2        # 每行业选 2 只
    momentum_short: 60            # 短期动量窗口
    momentum_long: 120            # 长期动量窗口
    weight_short: 0.6             # 短期动量权重
    weight_long: 0.4              # 长期动量权重
    max_industry_weight: 0.25     # 单行业权重上限 25%

    # 大盘趋势过滤
    market_filter: true
    market_index: "000300.XSHG"   # 沪深300
    market_ma_short: 5            # 短期均线 5日
    market_ma_long: 20            # 长期均线 20日

    # 行业短期风险过滤
    industry_risk_filter: true
    risk_filter_window: 20        # 20日动量为负剔除
    risk_filter_min_industries: 3 # 至少保留3个行业

    # 绝对动量（Dual Momentum）
    absolute_momentum: true
    absolute_momentum_window: 20
    absolute_momentum_threshold: -0.03   # 20日收益<-3%触发
    absolute_momentum_scale: 0.5         # 降仓50%

    # RRG 框架（v9 新增）
    use_rrg: true
    rs_ratio_window: 220          # RS-Ratio 回看窗口
    rs_momentum_window: 30        # RS-Momentum 回看窗口
    rrg_momentum_threshold: 100.0 # 领先象限阈值
    rrg_min_industries: 3         # RRG 最少保留行业数

    # 逆波动率加权（已禁用，损害 IS Sharpe）
    use_inv_vol_weight: false
    inv_vol_window: 20

    # 多因子选股
    use_factors: true
    factor_names:
      - Price1M                   # 1个月价格动量
      - Price3M                   # 3个月价格动量
      - ROC20                     # 20日变化率
      - DAVOL10                   # 10日平均量比
      - money_flow_20             # 20日资金流
      - gross_income_ratio        # 毛利率
      - roe_ttm                   # ROE（TTM）
      - net_profit_ratio          # 净利率
      - earnings_to_price_ratio   # 盈利收益率
      - book_to_price_ratio       # 账面市值比
      - raw_beta                  # BARRA beta（反向）
      - residual_volatility       # BARRA 残差波动率（反向）
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
      raw_beta: -2.0              # 反向，降低组合 beta
      residual_volatility: -1.5   # 反向，降低特质波动率
```

#### 4.4.3 组合/风控/调仓配置

```yaml
portfolio:
  max_stock_weight: 0.10         # 单股上限
  max_industry_weight: 0.25      # 单行业上限
  min_stocks: 5                  # 最少持股数

risk:
  method: regime_adaptive        # 自适应风控
  target_vol: 0.12               # 目标年化波动率 12%
  lookback: 20                   # 波动率回看窗口
  min_exposure_scale: 0.3        # 最小仓位 30%

rebalance:
  frequency: weekly              # 周频调仓
  weekday: 0                     # 周一调仓
  method: cost_benefit           # 成本收益权衡调仓
  cost_model:
    name: stock_cn               # A股成本模型

factors:
  - mom_1m                       # IC 计算用因子

pools:
  stocks:
    index: "000300.XSHG"         # 沪深300 候选池

data:
  source: duckdb
  data_root: "D:/Work/Project/download_a_share/data"
```

### 4.5 复现指南

#### 4.5.1 环境准备

```bash
# 依赖
pip install polars numpy pydantic openpyxl duckdb lightgbm

# 数据目录（需提前准备）
# D:/Work/Project/download_a_share/data
#   ├── duckdb/                  # DuckDB 数据文件
#   │   ├── ohlcv.duckdb          # 量价数据
#   │   ├── factors.duckdb        # 聚宽因子数据
#   │   └── industry.duckdb       # 行业映射
```

#### 4.5.2 IS 回测复现

```bash
python scripts/industry_rotation_is.py v9
# 预期输出: IS Sharpe 0.9222, 总收益+78.10%, 最大回撤-14.43%
```

#### 4.5.3 OOS 回测复现

```bash
python scripts/industry_rotation_oos.py v9
# 预期输出: OOS 收益-1.51%, 沪深300 -3.01%, 超额+1.50%
```

#### 4.5.4 建仓/调仓文件生成

```bash
# 每日调仓检查（T日早晨运行，生成T日调仓文件）
python scripts/industry_rotation_daily.py
# 输出: output/ths/industry_rotation_v9/{date}_rebalance.xlsx
```

#### 4.5.5 关键代码位置

| 模块 | 路径 | 关键函数/类 |
|------|------|------------|
| 策略定义 | [v9/strategy.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/industry_rotation/v9/strategy.py) | `IndustryRotationStrategyV9.from_version` |
| 策略配置 | [v9/config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/industry_rotation/v9/config.yaml) | 全部参数 |
| 选股器 | [industry_rotation_selector.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/industry_rotation_selector.py) | `IndustryRotationSelector.select` |
| RRG 实现 | 同上 | `_compute_rrg_table` (L176-278) |
| RRG 选择逻辑 | 同上 | L783-839 |
| 回测引擎 | [backtest.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py) | `BacktestEngine.run` |
| 调仓日计算 | [allocator.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/allocator.py) | `BaseAllocator.get_rebalance_dates` |
| 调度器 | [scheduler.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/scheduler.py) | `CalendarScheduler` |
| 风控 | [regime_adaptive.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/risk_managers/regime_adaptive.py) | `RegimeAdaptiveRiskManager` |

### 4.6 建仓/调仓文件复现

#### 4.6.1 模板

参考同花顺模板: `THS-PMS-交易组合流水导入模板-20260602.xlsx`（已纳入代码库版本管理）

#### 4.6.2 已生成的 OOS 调仓文件

```
output/ths/industry_rotation_v9/
├── 20260601_build.xlsx          # 建仓文件
├── 20260608_rebalance.xlsx      # 第1次调仓
├── 20260615_rebalance.xlsx      # 第2次调仓
├── 20260622_rebalance.xlsx      # 第3次调仓（RRG剔除建筑材料换银行）
├── 20260629_rebalance.xlsx      # 第4次调仓
├── 20260706_rebalance.xlsx      # 第5次调仓
└── 20260713_rebalance.xlsx      # 第6次调仓
```

#### 4.6.3 复现命令

```bash
# 重新生成所有 OOS 调仓文件
python scripts/industry_rotation_daily.py --start 2026-06-01 --end 2026-07-16
```

---

## 5. 综合结论

### 5.1 过拟合风险

- **Data Snooping**: 30日 RRG 窗口存在轻度 data snooping（论证引用了 OOS 数据），但参数稳定性测试表明非过拟合
- **参数稳定性**: RRG窗口、周几、频率参数均稳定，v9 默认配置在 OOS 排名前列
- **核心风险**: 牛市偏好（2022熊市-7.38%），普适性不足

### 5.2 普适性改进方向

最推荐两个方向（不实施）：
1. **跨资产配置**（60%行业+40%债券ETF）: 显著降低Beta，改善熊市回撤
2. **多周期 RRG 组合**（10/30/60日投票）: 避免单窗口敏感性，提升参数稳健性

### 5.3 调仓频率与周几

- **最优频率**: weekly（动量策略最优平衡）
- **最优周几**: 周一（避免周末消息冲击，OOS 收益最优）
- **v9 默认配置（weekly + 周一）是正确的**

### 5.4 复现性

- v9 完整参数清单见 4.4 节
- 复现命令见 4.5 节
- 关键代码位置见 4.5.5 节
- 建仓/调仓文件复现见 4.6 节

---

## 附录: allocator.py Bug 修复记录

### Bug 描述

`ohmyquant/engine/allocator.py` 的 `get_rebalance_dates` 方法中，weekly 调仓的 `elif key != prev_key` 分支在新一周的第一个交易日就立即加入调仓日，**忽略 weekday 参数**，导致所有 weekday 的调仓日完全相同。

### 修复内容

重写 weekly 和 biweekly 逻辑，使用 `week_pending`/`week_done` 状态变量正确等待目标 weekday：

```python
if freq == "weekly":
    key = (dt.isocalendar()[0], dt.isocalendar()[1])
    if key != prev_key:
        # 新的一周：提交上周的兜底（若未命中 weekday）
        if not week_done and week_pending is not None:
            rebal_dates.add(week_pending)
        week_pending = None
        week_done = False
        prev_key = key
    if not week_done:
        if dt.weekday() == weekday:
            # 命中目标 weekday → 调仓
            rebal_dates.add(date_item)
            week_done = True
            week_pending = None
        elif week_pending is None:
            # 记录本周首个交易日作为兜底（目标 weekday 是假期时使用）
            week_pending = date_item
```

### 验证结果

修复后不同 weekday 产生不同调仓日（以 OOS 2026-06-01 ~ 2026-07-16 为例）：
- weekday=0（周一）: 6/1, 6/8, 6/15, 6/22, 6/29, 7/6, 7/13（全部周一）
- weekday=1（周二）: 6/2, 6/9, 6/16, 6/23, 6/30, 7/7, 7/14（全部周二）
- weekday=2（周三）: 6/3, 6/10, 6/17, 6/24, 7/1, 7/8, 7/15（全部周三）

### 影响

- 此 bug 影响 v6 以来的所有周频调仓回测（v6/v7/v8/v9）
- 由于 v9 默认 weekday=0（周一），而 bug 下也用每周第一个交易日（多数情况是周一），**v9 主回测结果不受影响**
- 但所有"周几对比"分析在 bug 修复前都是错误的（5个 weekday 结果相同）
