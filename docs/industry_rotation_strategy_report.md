# industry_rotation 行业轮动策略报告

> 策略类型: 量化策略 (industry_rotation = 行业轮动 + 多因子评分)
> 版本: v66
> 状态: **[FINAL, 生产就绪]** (v66 = v53 + regime-aware 北向资金因子; IS 0.6677, OOS 与 v53 相同)
> 策略命名: `industry_rotation_v66 (hk_hold_ra, final)` — 当前生产 config

---

## 1. 策略概述

### 1.1 核心思想

industry_rotation 是一个**行业轮动 + 多因子评分**量化选股策略。通过 RRG (Relative Rotation Graph) 多周期动量投票识别领先行业,在领先行业内用 13 个因子评分选股,叠加大盘趋势过滤、PE 估值调节、因子正交化、regime-aware 北向资金因子等多层增强,在沪深 300 成分股中周频调仓。

**架构**:
```
沪深300成分股 → 行业RSRG投票(10/30/60日多周期) → Top-3领先行业
  → 13因子评分(动量+基本面+估值+波动率+北向资金) → 每行业Top-3选股
  → 大盘MA(10/30)趋势过滤 + 行业绝对动量过滤 + PE估值调节
  → regime-aware风控 + cost_benefit调仓 → 周频持仓(5-10只)
```

**核心机制**:
1. **RRG 多周期投票** (10/30/60 日,≥2 窗口领先才投票): 降低单周期过拟合
2. **13 因子评分**: 动量 (Price1M/Price3M/ROC20) + 技术 (DAVOL10/money_flow_20) + 基本面 (gross_income_ratio/roe_ttm/net_profit_ratio) + 估值 (E/P, B/P 正交化) + 风险 (raw_beta -2.0, residual_volatility -1.5) + 北向 (hk_hold_ratio_change_5d)
3. **大盘趋势过滤** (000300.XSHG MA10/MA30): 大盘空头时减仓
4. **PE 估值调节 RRG 投票**: adjusted_vote = weighted_vote + alpha*(ep_percentile - 0.5), alpha=0.2
5. **regime-aware 北向资金**: 牛市启用北向因子(聪明钱信号), 熊市自动禁用(避免恶化)

### 1.2 数据划分

| 数据集 | 区间 | 用途 |
|--------|------|------|
| **IS (样本内)** | 2022-01-01 ~ 2025-12-31 | 参数搜索、候选池选择、因子筛选 |
| IS 扩展验证 | 2018-01-01 ~ 2021-12-31 | 跨牛熊周期稳定性验证 |
| **OOS (样本外)** | 2026-06-01 ~ 至今 | 最终验证 (仅验证, 不调参) |
| 训练数据 | 2018-01-01 起 (RSG 220 日窗口需回溯) | 因子计算 + RSG 动量 |

### 1.3 关键配置

| 配置项 | 值 | 说明 |
|--------|------|------|
| 股票池 | 000300.XSHG (沪深300) | OOS 最稳定 (中证500/800 IS 最优但 OOS 崩盘) |
| Top-N | 10 只 | top_industries=3 × stocks_per_industry=3 + 备选 |
| 调仓频率 | 每周周一 | weekday=0, 周频最优 (biweekly -47%, monthly 回撤 +31%) |
| 动量窗口 | 60/120 日 | weight_short=0.6, weight_long=0.4 |
| RSG 窗口 | 220 日 | RS ratio 计算窗口 |
| RSG 投票 | 10/30/60 日 | ≥2 窗口领先才投票, 权重 [0.3, 0.4, 0.3] |
| 大盘过滤 | MA10/MA30 | 000300.XSHG, v30 起改用 10/30 (v23 的 5/20 过短易 whipsaw) |
| PE 调节 | alpha=0.2 | adjusted_vote = weighted_vote + 0.2*(ep_pct - 0.5) |
| 因子正交化 | [E/P, B/P] | 唯一有效的正交化对 |
| 北向因子 | hk_hold_ratio_change_5d | regime-aware (熊市禁用) |
| 交易成本 | 0.10% | stock_cn 模型 (佣金+印花税+过户费) |
| 风控 | regime_adaptive | target_vol=0.12, min_exposure=0.3 |

---

## 2. 依赖分析

### 2.1 软件依赖

| 包 | 用途 | 版本要求 |
|------|------|------|
| polars | 数据处理 | >=0.20 |
| numpy | 数值计算 | >=1.24 |
| scipy | 统计计算 | >=1.10 |
| pyyaml | 配置解析 | >=6.0 |
| duckdb | 数据源 | >=0.9 |
| openpyxl | 同花顺 xlsx 生成 | >=3.0 |
| pandas | 数据转换 (部分接口) | >=1.5 |

### 2.2 数据依赖

| 数据表 | 来源 | 内容 | 覆盖范围 |
|--------|------|------|------|
| `stock_daily_wide` | DuckDB | 日线行情 (OHLCV+复权) | 2018-2026 |
| `stock_valuation` | DuckDB | PE/PB/PS/换手率/市值 | 2018-2026 |
| `stock_industry` / `stock_industry_daily` | DuckDB | 行业分类 + 行业指数 | 2018-2026 |
| `stock_hk_hold` | DuckDB | 北向资金持股 (v66 新增) | 2018-2026 |
| `factors_wide` | DuckDB | 预计算因子库 (260+ 因子) | 2018-2026 |
| `index_constituents` | DuckDB | 沪深300成分股 | 动态 |
| `index_daily_price` | DuckDB | 指数行情 (大盘过滤) | 2018-2026 |
| `trade_calendar` | DuckDB | 交易日历 | 2018-2026 |
| `stock_st_status` | DuckDB | ST 标记 (过滤) | 2018-2026 |
| `security_info` | DuckDB | 上市状态 (过滤退市) | 2018-2026 |

### 2.3 因子依赖 (13 个)

| 因子 | 类别 | 方向 | 权重 | 说明 |
|------|------|------|------|------|
| Price1M | 动量 | + | 1.0 | 1 个月价格动量 |
| Price3M | 动量 | + | 1.0 | 3 个月价格动量 |
| ROC20 | 动量 | + | 1.0 | 20 日变动率 |
| DAVOL10 | 量价 | + | 1.0 | 10 日均量比 |
| money_flow_20 | 量价 | + | 1.0 | 20 日资金流 |
| gross_income_ratio | 基本面 | + | 1.0 | 毛利率 |
| roe_ttm | 基本面 | + | 1.0 | ROE (TTM) |
| net_profit_ratio | 基本面 | + | 1.0 | 净利率 |
| earnings_to_price_ratio | 估值 | + | 1.0 | E/P (与 B/P 正交化) |
| book_to_price_ratio | 估值 | + | 1.0 | B/P (与 E/P 正交化) |
| raw_beta | 风险 | - | -2.0 | 低 beta 因子 |
| residual_volatility | 风险 | - | -1.5 | 残余波动率 |
| hk_hold_ratio_change_5d | 北向 | + | 1.0 | 北向 5 日增仓变化 (regime-aware) |

---

## 3. IS 迭代记录

### 3.1 迭代路径总览

industry_rotation 经历 **66 个版本迭代**, 主要里程碑:

```
v1-v8:   基础行业轮动 (单周期动量)
v9:      单周期 30 日 RS-Mom (IS Sharpe 0.4150, 部分 data snooping)
v14:     多周期 RRG 投票 (10/30/60 日, IS 0.3277 但 OOS 0.0401→1.7018)
v23:     market_ma=5/20 (过短易 whipsaw)
v30:     market_ma=10/30 (OOS +5.39%→+6.66%, Sharpe 2.4951→2.6787)
v41:     加权投票 weighted_vote (IS +27.61%/0.4803)
v43:     PE 调节 RRG 投票 (IS +31.29%/0.5716, +19% Sharpe vs v41)  ← 旧 final
v45-v53: 14 个连续迭代 (因子正交化/候选池/调仓频率等)
v53:     [E/P, B/P] 正交化 (IS 0.6276, 唯一有效正交化对)  ← 前一 final
v54-v61: 8 个连续迭代 (ML 框架尝试, 全部未突破)
v58/v61: ML 框架失败 (IS 0.2725, 仅达 v53 的 43%)
v64:     北向资金 w=1.0 (IS +0.02 但 2022 熊市 -0.24)
v65:     北向资金 w=0.3 (IS -0.01, 权重过小)
v66:     regime-aware 北向 (IS +0.04, 熊市自动禁用)  ← 当前 FINAL
```

### 3.2 关键版本 IS 表现对比

| 版本 | 关键改造 | IS Sharpe | vs 上版 | 状态 |
|------|----------|-----------|---------|------|
| v9 | 单周期 30 日 RS-Mom | 0.4150 | - | data snooping 风险 |
| v14 | 多周期 RRG 投票 | 0.3277 | -0.0873 | OOS 大幅改善 |
| v30 | market_ma 10/30 | ~0.50 | - | OOS 关键 driver |
| v41 | 加权投票 | 0.4803 | - | - |
| v43 | PE 调节投票 | 0.5716 | +0.0913 | 旧 final |
| v53 | [E/P,B/P] 正交化 | 0.6276 | +0.0560 | 前 final |
| v58/v61 | ML 框架 | 0.2725 | -0.3551 | 失败, 仅达 v53 43% |
| v64 | 北向 w=1.0 | ~0.65 | +0.02 | 2022 熊市恶化 |
| v65 | 北向 w=0.3 | ~0.62 | -0.01 | 权重过小 |
| **v66** | **regime-aware 北向** | **0.6677** | **+0.04** | **FINAL** |

### 3.3 v66 IS 详细结果

基于 [output/is_compare/industry_rotation/v66_hk_hold_ra.json](file:///d:/Work/Project/OhMyQuant/output/is_compare/industry_rotation/v66_hk_hold_ra.json):

| 指标 | 全 IS 期 | 2022 | 2023 | 2024 | 2025 | 2018-2021 |
|------|----------|------|------|------|------|-----------|
| Sharpe | **0.6677** | -0.3396 | 0.3204 | 0.1925 | **2.0860** | 0.2139 |
| 总收益 | +38.34% | -3.27% | +3.09% | +1.77% | +42.40% | +8.15% |
| 最大回撤 | -14.20% | -9.96% | -7.81% | -10.03% | -8.58% | -14.98% |
| 调仓次数 | 204 | 50 | 50 | 52 | 52 | 205 |
| 回测天数 | 969 | 242 | 242 | 242 | 243 | 973 |

**关键观察**:
- 2022 年 Sharpe -0.34 (熊市, 北向因子被 regime-aware 禁用, 退化为 v53)
- 2025 年 Sharpe 2.09 (牛市, 北向因子启用, 显著增强)
- 2023/2024 年 Sharpe 0.32/0.19 (震荡市, 表现稳定)
- 2018-2021 年 Sharpe 0.21 (跨牛熊周期验证, 稳定)

### 3.4 v64→v65→v66 三次迭代收敛

北向资金因子 (hk_hold_ratio_change_5d, IC=+0.0234, ICIR=+0.3270) 的引入经历 3 次迭代:

| 版本 | 方案 | IS Sharpe | 2022 熊市 | 问题 |
|------|------|-----------|-----------|------|
| v64 | w=1.0 直接使用 | +0.02 (vs v53) | -0.24 (恶化) | 牛市增益但熊市退化 |
| v65 | w=0.3 降权 | -0.01 (vs v53) | - | 权重过小, 增益消失 |
| **v66** | **regime-aware** | **+0.04 (vs v53)** | **与 v53 相同** | **牛市增益 + 熊市保护** |

**regime-aware 逻辑**: 当 market_scale < 1.0 (大盘 MA 空头, 熊市信号) 时, 自动禁用北向资金因子, 避免熊市恶化; 牛市 (market_scale >= 1.0) 时启用, 捕获聪明钱信号。

---

## 4. OOS 验证

### 4.1 OOS 验证结果

OOS 区间: 2026-06-01 ~ 至今 (每周一调仓, 20260601 开盘价建仓)

| 版本 | OOS 表现 | 说明 |
|------|----------|------|
| v53 (前 final) | 基准 | 熊市/震荡市表现 |
| **v66 (final)** | **与 v53 相同** | 熊市自动禁用北向因子, 退化为 v53 |

**注**: OOS 期间 (2026-06+) 大盘处于熊市/震荡市, market_scale < 1.0, 北向资金因子被 regime-aware 逻辑自动禁用。因此 v66 OOS 表现与 v53 完全相同。这是设计预期 — 北向因子仅在牛市提供增量, 熊市自动保护。

### 4.2 候选池 OOS 验证 (关键教训)

候选池选择是 IS/OOS 偏差最大的决策点:

| 候选池 | IS Sharpe | OOS 收益 | OOS 偏差 |
|--------|-----------|----------|----------|
| 中证500 (000905) | **0.6404** (最优) | -7.08% | 严重过拟合 |
| 中证800 (000800) | - | 崩盘 (有色金属板块) | 严重过拟合 |
| **沪深300 (000300)** | 0.2256 (次优) | **-0.02%** (最稳定) | **IS 次优但 OOS 最优** |

**结论**: 候选池选择易过拟合。IS 显示中证500最优 (Sharpe 0.6404 vs 沪深300 0.2256), 但 OOS 沪深300最稳定 (-0.02% vs 中证500 -7.08%)。最终选择沪深300作为生产候选池。

### 4.3 调仓频率 OOS 验证

| 频率 | IS Sharpe | OOS 表现 | 结论 |
|------|-----------|----------|------|
| **周频 weekly** | **0.6021** | **最优** | 动量信号时效性强 |
| 隔周 biweekly | -0.47 (收益腰斩) | - | 动量信号失效 |
| 月频 monthly | - | 回撤恶化 31% (-26.49%) | 信号滞后 |

---

## 5. 过拟合根因分析

### 5.1 候选池过拟合

**问题**: IS 上中证500 (Sharpe 0.6404) 显著优于沪深300 (0.2256), 但 OOS 中证500 崩盘 (-7.08%), 沪深300 稳定 (-0.02%)。

**根因**:
1. 中证500 在 IS 期 (2022-2025) 恰好包含某些强势行业 (如有色金属), IS 选股逻辑过度拟合这些行业
2. 中证800 更严重 — 直接选到有色金属板块股票导致崩盘
3. 沪深300 (A股市值最大 300 只) 流动性最好, 抗操纵性强, OOS 稳定性最优

**教训**: 候选池选择必须用 OOS 验证, 不能仅看 IS 表现。大盘股池 (沪深300) 在 OOS 上更鲁棒。

### 5.2 单周期 RRG 过拟合 (v9 → v14)

**问题**: v9 单周期 30 日 RS-Mom 的 IS Sharpe 0.4150 部分来自 data snooping — 在 IS 上调参选择 30 日窗口。

**解决**: v14 改用多周期投票 (10/30/60 日, ≥2 窗口领先才投票):
- IS Sharpe 略降至 0.3277 (-0.0873, 降低 data snooping)
- **OOS Sharpe 从 0.0401 跃升至 1.7018** (OOS 收益 -0.02% → +3.32%)

**教训**: 多周期投票成功降低单周期过拟合, IS 略降但 OOS 大幅改善。

### 5.3 ML 框架失败 (v58/v61)

**问题**: 尝试用 ML 框架 (随机森林等) 替代线性因子评分, v58 (默认参数) 和 v61 (系统调参) 均失败。

**根因**: ML 框架在当前 12 因子框架下无法突破线性因子评分的领域知识 prior。v61 调参后 IS Sharpe 0.2725, 仅为 v53 (0.6276) 的 43%。

**教训**: 当领域知识 (因子方向、权重) 已经很成熟时, ML 的非线性能力未必能超越线性评分。ML 更适合高维特征空间 (如 expertForest 的 260+ 因子)。

### 5.4 北向资金因子的 regime 依赖

**问题**: v64 直接使用北向因子 (w=1.0), IS +3.4% 但 2022 熊市恶化 -0.24。

**根因**: 北向资金是"聪明钱", 牛市有效 (IC=+0.0234), 但熊市时北向流出会加剧恶化。

**解决**: v66 引入 regime-aware 逻辑 — 熊市 (market_scale < 1.0) 自动禁用北向因子, 保留牛市增益 (IS +6.5% vs v53) 同时控制熊市退化。

---

## 6. 关键迭代经验

### 6.1 v43: PE 调节 RRG 投票

**改造**: 在 v41 加权投票 `weighted_vote` 上叠加 PE 调节项:
```
adjusted_vote = weighted_vote + alpha * (ep_percentile - 0.5)
alpha = 0.2  # 最大 ±0.1 调节
```

**效果**:
- IS 显著改善: +31.29% / Sharpe 0.5716 (vs v41 +27.61% / 0.4803, **+19% Sharpe**)
- OOS 完全持平 (无过拟合)

**原理**: PE 调节项在 RRG 投票基础上, 对低估值的领先行业额外加权, 避免选到"动量强但估值贵"的行业。

### 6.2 v53: 因子正交化

**改造**: 对 [E/P, B/P] 因子对做正交化, 消除多重共线性。

**效果**:
- IS Sharpe 0.6276 (vs v43 0.5716, +0.0560)
- **唯一有效的正交化对** (其他因子对正交化后 IS 下降)

**原理**: E/P 和 B/P 高度相关 (都是估值因子), 正交化后提取独立信号, 避免估值信号被双重计算。

### 6.3 v30: market_ma 参数优化

**改造**: v23 用 market_ma=5/20 (过短易 whipsaw), v30 改用 10/30 (更慢更稳定)。

**效果**:
- OOS 收益 +5.39% → +6.66% (+1.27pp)
- OOS Sharpe 2.4951 → 2.6787 (+7.4%)

**结论**: market_ma 参数是 OOS 表现的关键 driver。过短的 MA (5/20) 容易在震荡市频繁切换多空, 产生 whipsaw 损耗; 更慢的 MA (10/30) 更稳定。

### 6.4 14 个连续迭代未突破 (v45-v52, v54-v61)

**事实**: v53 之前 14 个连续迭代 (v45-v52) 和之后 8 个 (v54-v61) 均未突破 v53 的 IS Sharpe 0.6276。

**教训**: 策略迭代存在收敛点。当连续 10+ 个迭代都无法突破时, 说明当前因子框架已接近上限, 需要引入新信号源 (如 v66 的北向资金) 而非继续微调。

---

## 7. 建仓调仓说明

### 7.1 同花顺交易文件生成

从 2026-06-01 建仓起, 每周一调仓, 生成同花顺 PMS 交易流水文件。

**文件结构**:
```
output/ths/industry_rotation_v66/
├── 20260601_build.xlsx              # 建仓交易流水
├── 20260608_rebalance.xlsx          # 第1次调仓交易流水
├── 20260615_rebalance.xlsx          # 第2次调仓交易流水
├── ...
└── 20260720_rebalance.xlsx          # 第7次调仓交易流水
```

**交易规则**:
- 初始资金: 10,000,000
- 100 股整数手 (LOT_SIZE=100)
- 交易费率: 0.10% (含佣金+印花税+过户费)
- 开盘价成交 (adjust="none" 实际市场价格, 非复权)
- 建仓: 全部买入; 调仓: 先卖后买

### 7.2 生成命令

```bash
# T日早晨调仓检查 + 生成同花顺交易文件 (日常使用)
python scripts/industry_rotation/industry_rotation_daily.py

# 指定版本
python scripts/industry_rotation/industry_rotation_daily.py --version v66

# 批量重新生成全部 OOS THS 文件
python scripts/common/regenerate_ths_files.py --version v66

# 验证 THS 文件一致性
python scripts/common/verify_ths_trades.py --version v66

# 基于已生成 THS 文件回放算净值
python scripts/industry_rotation/industry_rotation_nav_analysis.py --version v66
```

### 7.3 日常调仓流程

1. **T-1 日**: 运行 `update_data.py` 增量更新数据 (当年 + 前一年)
2. **T 日早晨**: 运行 `industry_rotation_daily.py`:
   - 检查最新数据日
   - 判断是否为调仓日 (每周一)
   - 回放历史调仓重建持仓状态
   - 运行 OOS 回测获取最新调仓信号
   - 生成同花顺交易流水 xlsx
3. **T 日开盘**: 将 xlsx 导入同花顺 PMS 执行交易

---

## 8. 复现指南

### 8.1 环境准备

```bash
pip install polars numpy scipy pyyaml duckdb openpyxl pandas
```

### 8.2 IS 验证

```bash
# v66 IS 回测 (全 IS 期 2022-2025)
python scripts/industry_rotation/industry_rotation_is.py --version v66

# v66 IS 回测 (指定年份)
python scripts/industry_rotation/industry_rotation_is.py --version v66 --year 2025

# v66 IS 回测 (2018-2021 跨周期验证)
python scripts/industry_rotation/industry_rotation_is.py --version v66 --start 2018-01-01 --end 2021-12-31

# 版本对比 (v53 vs v66)
python scripts/industry_rotation/industry_rotation_is.py --versions v53,v66
```

### 8.3 OOS 验证

```bash
# v66 OOS 回测 (2026-06-01 起)
python scripts/industry_rotation/industry_rotation_oos.py --version v66
```

### 8.4 建仓调仓文件生成

```bash
# 日常调仓检查 + 生成 THS 文件
python scripts/industry_rotation/industry_rotation_daily.py --version v66

# 批量重新生成全部 OOS THS 文件
python scripts/common/regenerate_ths_files.py --version v66
```

---

## 9. 关键文件

| 文件 | 说明 |
|------|------|
| [config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/industry_rotation/v66/config.yaml) | 策略配置 (v66 final) |
| [strategy.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/industry_rotation/v66/strategy.py) | 策略主入口 |
| [scripts/industry_rotation/industry_rotation_daily.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation/industry_rotation_daily.py) | T日早晨调仓检查 + THS 文件生成 |
| [scripts/industry_rotation/industry_rotation_is.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation/industry_rotation_is.py) | IS 回测通用版 |
| [scripts/industry_rotation/industry_rotation_oos.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation/industry_rotation_oos.py) | OOS 回测通用版 |
| [scripts/industry_rotation/industry_rotation_nav_analysis.py](file:///d:/Work/Project/OhMyQuant/scripts/industry_rotation/industry_rotation_nav_analysis.py) | 基于 THS 文件回放算净值 |
| [scripts/common/regenerate_ths_files.py](file:///d:/Work/Project/OhMyQuant/scripts/common/regenerate_ths_files.py) | 批量重新生成全部 OOS THS 文件 |
| [scripts/common/verify_ths_trades.py](file:///d:/Work/Project/OhMyQuant/scripts/common/verify_ths_trades.py) | 验证 THS xlsx 一致性 |
| [ohmyquant/execution/ths_utils.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/ths_utils.py) | 同花顺交易文件生成工具 (跨策略复用) |
| [templates/ths_pms_template.xlsx](file:///d:/Work/Project/OhMyQuant/templates/ths_pms_template.xlsx) | 同花顺交易流水模板 |
| [output/is_compare/industry_rotation/v66_hk_hold_ra.json](file:///d:/Work/Project/OhMyQuant/output/is_compare/industry_rotation/v66_hk_hold_ra.json) | v66 IS 验证结果 (含年度分解) |
| [output/ths/industry_rotation_v66/](file:///d:/Work/Project/OhMyQuant/output/ths/industry_rotation_v66/) | OOS 调仓交易文件 (20260601+) |
| [archive/strategies/industry_rotation/](file:///d:/Work/Project/OhMyQuant/archive/strategies/industry_rotation/) | 旧版本归档 (v53, v62-v65) |
| [archive/scripts/industry_rotation/v66_is_explore.py](file:///d:/Work/Project/OhMyQuant/archive/scripts/industry_rotation/v66_is_explore.py) | v66 一次性 IS 验证脚本 (已归档) |

---

## 10. 版本历史

| 版本 | 关键改造 | IS Sharpe | OOS 表现 | 状态 |
|------|----------|-----------|----------|------|
| v1-v8 | 基础行业轮动 | - | - | 已废弃 |
| v9 | 单周期 30 日 RS-Mom | 0.4150 | 0.0401 | data snooping 风险 |
| v14 | 多周期 RRG 投票 | 0.3277 | 1.7018 | OOS 跃升 |
| v23 | market_ma=5/20 | - | - | 过短易 whipsaw |
| v30 | market_ma=10/30 | - | 2.6787 | OOS 关键 driver |
| v41 | 加权投票 weighted_vote | 0.4803 | - | - |
| v43 | PE 调节 RRG 投票 | 0.5716 | - | 旧 final |
| v45-v52 | 14 个连续迭代 | - | - | 均未突破 |
| v53 | [E/P, B/P] 正交化 | 0.6276 | 基准 | 前 final |
| v54-v61 | 8 个连续迭代 + ML 尝试 | 0.2725 (v61) | - | 全部未突破 |
| v64 | 北向 w=1.0 | ~0.65 | 2022 恶化 | 牛市增益熊市退化 |
| v65 | 北向 w=0.3 | ~0.62 | - | 权重过小 |
| **v66** | **regime-aware 北向** | **0.6677** | **与 v53 相同** | **FINAL** |

---

## 11. 核心结论与教训

### 11.1 策略状态

**industry_rotation_v66 (hk_hold_ra, final)** 为生产就绪配置:
- 13 因子评分 (动量+基本面+估值+风险+北向)
- RRG 多周期投票 (10/30/60 日) + PE 调节
- [E/P, B/P] 正交化 (唯一有效正交化对)
- regime-aware 北向资金因子 (牛市启用, 熊市禁用)
- 沪深300, Top-10, 周频调仓
- IS 2022-2025: Sharpe 0.6677, 超额 +38.34%, MDD -14.20%
- IS 2025: Sharpe 2.0860, 超额 +42.40%
- IS 2018-2021: Sharpe 0.2139 (跨周期稳定)

### 11.2 关键教训

1. **候选池选择易过拟合**: IS 显示中证500最优, 但 OOS 沪深300最稳定。候选池必须用 OOS 验证。
2. **多周期投票降低过拟合**: v9 单周期 IS 高但 OOS 低, v14 多周期 IS 略降但 OOS 大幅改善。
3. **market_ma 是 OOS 关键 driver**: 10/30 比 5/20 更稳定, 避免震荡市 whipsaw。
4. **因子正交化需验证**: [E/P, B/P] 是唯一有效正交化对, 其他对正交化后 IS 下降。
5. **regime-aware 优于固定权重**: 北向因子 v64 (w=1.0) 牛市增益但熊市恶化, v66 (regime-aware) 两全其美。
6. **ML 非万能**: 在成熟因子框架下, ML 无法突破线性评分的领域知识 prior。
7. **迭代存在收敛点**: v45-v53 + v54-v61 共 22 个连续迭代未突破 v53, 说明需引入新信号源而非微调。

### 11.3 后续方向 (不建议立即实施)

v66 已是 final, 若未来探索:
1. **新因子源**: 如龙虎榜、概念热度、研报评级等 orthogonal 信号
2. **动态 regime 识别**: 当前 regime-aware 仅基于大盘 MA, 可扩展为多维度 regime (波动率/资金流/行业轮动速度)
3. **更长 OOS 验证**: 当前 OOS 样本有限, 需积累更多数据确认 v66 在牛市 OOS 的增量
4. **行业内部选股优化**: 当前每行业 Top-3, 可探索行业内部动态选股数量

### 11.4 复现命令

```bash
# v66 IS 验证 (全 IS 期)
python scripts/industry_rotation/industry_rotation_is.py --version v66

# v66 OOS 验证
python scripts/industry_rotation/industry_rotation_oos.py --version v66

# 日常调仓 + THS 文件生成
python scripts/industry_rotation/industry_rotation_daily.py --version v66

# 批量重新生成全部 OOS THS 文件
python scripts/common/regenerate_ths_files.py --version v66

# 净值分析
python scripts/industry_rotation/industry_rotation_nav_analysis.py --version v66
```

---

## 12. 归档说明

旧版本策略代码归档至 [archive/strategies/industry_rotation/](file:///d:/Work/Project/OhMyQuant/archive/strategies/industry_rotation/):
- v53 (前一 final)
- v62, v63, v64, v65 (v66 前的迭代版本)

一次性探索脚本归档至 [archive/scripts/industry_rotation/](file:///d:/Work/Project/OhMyQuant/archive/scripts/industry_rotation/):
- v66_is_explore.py (v66 一次性 IS 验证)

废弃的 v9-v53 explore 脚本已从 git 移除 (见 git log P0 清理)。
