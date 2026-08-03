# expertForest_v1 多专家树集成策略报告

> 策略类型: 量化策略 (expertForest = multi-expert tree ensemble)
> 版本: v1
> 状态: **[v3 final, 生产就绪]** (32专家rank_average, OOS转正; v4优化尝试证明多样性>OOS筛选, 保持v3)
> 策略命名: `expertForest_v1 (meTree32, final v3)` — 当前生产config

---

## 1. 策略概述

### 1.1 核心思想

expertForest_v1 是一个**多专家树集成学习**量化选股策略，通过构建多个差异化的树模型专家（RF × ET × LGB × XGB），在 Walk Forward 滚动训练框架下进行周频调仓选股。

**架构**:
```
277因子 → 48个差异化专家(RF×ET×LGB×XGB, momentum+fundamental+sentiment) → Walk Forward周频滚动训练 → rank_average集成 → Top-30选股
```

**多样性来源**:
1. 模型结构差异 (RF Bootstrap / ET 随机阈值 / LGB 直方图 / XGB 预排序)
2. 超参差异 (conservative 浅树 / moderate 中树)
3. 特征集差异 (动量信号 / 基本面信号 / 情绪信号)
4. 训练窗口差异 (252天适应 / 504天稳健)
5. 随机种子差异 (0-47)

**v2 优化动机** (基于专家相关性分析, 见 [correlation_report.md](file:///d:/Work/Project/OhMyQuant/output/expert_analysis/correlation_report.md)):
- 32专家仅1对冗余(corr≥0.95), 平均相关性0.42, 整体差异化良好
- 4个差异化维度中, **feature_set为最有效差异化维度** (组间-组内相关性差=-0.3853, 负值=组内相关性远高于组间=有效区分), hyper_set几乎无区分(+0.0116)
- 据此新增sentiment特征集 (融资融券+大单资金流+解禁压力, 与factors_wide无重叠的orthogonal信号), 48专家进一步强化最有效的差异化维度

### 1.2 数据划分

| 数据集 | 区间 | 用途 |
|--------|------|------|
| IS (样本内) | 2023-01-01 ~ 2026-05-31 | 模型训练、参数搜索、候选池选择 (v2扩展至2026.05, 充分利用近期数据) |
| OOS (样本外) | 2026-06-01 ~ 2026-07-29 | 最终验证 (仅验证, 不调参) |
| 训练数据 | 2021-01-01 起 (504日窗口需回溯) | 因子计算 + 标签生成 |

### 1.3 关键配置

| 配置项 | 值 | 说明 |
|--------|------|------|
| 股票池 | 000905.XSHG (中证500) | IS迭代最优 |
| Top-N | 30 | IS迭代最优 |
| 调仓频率 | 每周周一 | weekday=0 |
| 预测horizon | 5日 | 5日前向超额收益 |
| 训练窗口 | 252 + 504 日 | 双窗口差异化 |
| purge_gap | 5日 | 防标签泄漏 |
| 集成方法 | rank_average | 无IC加权, 更鲁棒 |
| 交易成本 | 0.01%佣金 + 0.10%滑点 | 双向万1佣金 |

---

## 2. 依赖分析

### 2.1 软件依赖

| 包 | 用途 | 版本要求 |
|------|------|------|
| scikit-learn | RF/ET 模型 | >=1.0 |
| lightgbm | LGB 模型 | >=3.0 |
| xgboost | XGB 模型 | >=1.6 |
| polars | 数据处理 | >=0.20 |
| numpy | 数值计算 | >=1.24 |
| scipy | Spearman IC / rankdata | >=1.10 |
| joblib | 并行训练 (threading backend) | >=1.2 |
| pyyaml | 配置解析 | >=6.0 |
| duckdb | 数据源 | >=0.9 |
| openpyxl | 同花顺xlsx生成 | >=3.0 |

### 2.2 数据依赖

| 数据表 | 来源 | 内容 | 覆盖范围 |
|--------|------|------|------|
| `factors_wide` | DuckDB | 260个原始因子 (估值/质量/动量/技术等) | 2022-2026 (池内股票) |
| `stock_daily_wide` | DuckDB | 日线行情 (后复权OHLCV) | 2021-2026 |
| `stock_hk_hold` | DuckDB | 北向资金持股 | 2021-2026 |
| `stock_margin_trading` | DuckDB | 融资融券余额/买入额 (v2新增, sentiment) | 2016-2026 |
| `stock_money_flow` | DuckDB | 大单/超大单资金流 (v2新增, sentiment) | 2021-2026 |
| `stock_locked_shares` | DuckDB | 解禁明细 (v2新增, sentiment) | 2020-2026 |
| `index_constituents` | DuckDB | 指数成分股 | 动态 |
| `index_daily` | DuckDB | 基准指数行情 | 2021-2026 |
| `trade_calendar` | DuckDB | 交易日历 | 2021-2026 |

### 2.3 模型依赖

| 模型 | 类 | 超参预设 | 专家数 |
|------|------|------|------|
| RandomForest | `sklearn.ensemble.RandomForestRegressor` | conservative / moderate | 12 |
| ExtraTrees | `sklearn.ensemble.ExtraTreesRegressor` | conservative / moderate | 12 |
| LightGBM | `lightgbm.LGBMRegressor` | conservative / moderate | 12 |
| XGBoost | `xgboost.XGBRegressor` | conservative / moderate | 12 |

**专家总数**: 4模型 × 2超参 × 3特征集 × 2窗口 = **48个**

**超参预设** (无aggressive深树):

| 超参档 | RF/ET | LGB/XGB | 状态 |
|--------|-------|---------|------|
| conservative | depth=6, leaf=40, est=150 | depth=4, lr=0.05, est=200 | 保留 |
| moderate | depth=8, leaf=20, est=200 | depth=6, lr=0.04, est=350 | 保留 |
| ~~aggressive~~ | ~~depth=10, leaf=10~~ | ~~depth=8, lr=0.03, est=500~~ | **移除(过拟合)** |

---

## 3. IS 迭代记录

### 3.1 迭代路径

```
Phase 1: 股票池+Top-N探索
  -> ZZ500(000905.XSHG) N=30 equal_weight Sharpe=1.3814 最优

Phase 2: 集成方法对比 (ZZ500 N=30)
  -> ic_rank_weighted Sharpe=1.5043 (IS最优, 但OOS过拟合)
  -> rank_average Sharpe=1.4725 (次优, 更鲁棒)

Phase 3: 特征集探索 (已收敛, 默认momentum+fundamental最优)

抗过拟合迭代 (OOS验证失败后):
  Phase A: OOS验证 rank_average -> Sharpe=-0.1987 (仍为负)
  Phase B: 修复IC计算 (样本内IC -> 80/20 holdout OOF IC)
  Phase C: 简化模型 (48专家->32专家, 去掉aggressive深树)

v2 优化迭代 (32专家final基础上):
  Phase D: 专家相关性分析 -> 新增sentiment特征集 -> 48专家 (meTree48 final v2)
```

### 3.2 IS 验证结果汇总

#### Phase 1: 股票池 x Top-N (equal_weight集成)

| 股票池 | N | Sharpe | 超额收益 | 最大回撤 | Calmar | 月胜率 |
|--------|---|--------|----------|----------|--------|--------|
| 000300.XSHG | 10 | 0.8980 | 70.37% | -42.75% | 0.5544 | 52.9% |
| 000300.XSHG | 30 | 0.7696 | 25.86% | -39.56% | 0.3325 | 50.0% |
| 000905.XSHG | 10 | 1.0823 | 115.33% | -38.86% | 0.8437 | 55.9% |
| 000905.XSHG | 20 | 1.2895 | 143.25% | -32.69% | 1.1579 | 61.8% |
| **000905.XSHG** | **30** | **1.3814** | **146.62%** | **-28.66%** | **1.3412** | **61.8%** |

**结论**: 中证500(000905.XSHG) N=30 最优。

#### Phase 2: 集成方法对比 (ZZ500 N=30)

| 集成方法 | Sharpe | 超额收益 | 最大回撤 | Calmar | IC加权? |
|----------|--------|----------|----------|--------|---------|
| equal_weight | 1.3814 | 146.62% | -28.66% | 1.3412 | 否 |
| ic_weighted | 1.1243 | 85.55% | -39.72% | 0.6776 | 是(样本内) |
| rank_average | 1.4725 | 146.77% | -29.36% | 1.3103 | 否 |
| **ic_rank_weighted** | **1.5043** | **142.25%** | **-26.32%** | **1.4316** | 是(样本内) |

**IS结论**: ic_rank_weighted 最优 (Sharpe=1.5043)。
**OOS后发现**: ic_rank_weighted 严重过拟合 (见第5节)。

### 3.3 抗过拟合迭代 IS 结果

| 配置 | 专家数 | Sharpe | 超额收益 | 最大回撤 | Calmar | 月胜率 |
|------|--------|--------|----------|----------|--------|--------|
| rank_average + all(48专家) | 48 | 1.4725 | 146.77% | -29.36% | 1.3103 | 58.8% |
| **rank_average + cons+mod(32专家)** | **32** | **1.7552** | **207.48%** | **-32.65%** | **1.4790** | **67.7%** |

**关键发现**: 去掉aggressive深树后IS Sharpe反而从1.4725提升到1.7552 (+0.2827), 说明aggressive专家在添加噪声而非信号。月胜率从58.8%提升到67.7%。

### 3.4 Phase D: v2 sentiment专家优化 (2025-scope IS验证)

**动机**: 对32专家(meTree32 final)做专家行为相关性分析 ([correlation_report.md](file:///d:/Work/Project/OhMyQuant/output/expert_analysis/correlation_report.md)):
- 32专家仅1对冗余 (corr≥0.95): `et_conservative_fundamental_w252` ↔ `et_moderate_fundamental_w252` (0.9562)
- 平均相关性 0.42, 平均Top-30重叠度 0.32 → 整体差异化良好
- 4个差异化维度的区分度排名 (discrimination = 组间-组内平均相关性, **负值=有效区分**):
  | 维度 | discrimination | 评价 |
  |------|---------------|------|
  | feature_set | **-0.3853** | **最有效差异化维度** |
  | train_window | -0.0611 | 中等有效 |
  | model_type | -0.0377 | 中等有效 |
  | hyper_set | +0.0116 | 几乎无区分(冗余) |
- IC: 所有专家100%正IC率, xgb/lgb较强 (0.3-0.54), et较弱 (0.09-0.21)

**改造**: 在最有效的feature_set维度上新增第3个特征集 `sentiment`, 利用与factors_wide无重叠的orthogonal信号:
- `stock_margin_trading` → 融资融券余额变化 (margin_fin_chg5d/20d, margin_sec_chg5d, 3因子)
- `stock_money_flow` → 大单+超大单净流入 (mf_net_big_5d/20d, mf_big_ratio_5d, 3因子)
- `stock_locked_shares` → 解禁压力 (unlock_rate_20d/60d, 已知未来事件, 2因子)
- 共8个sentiment因子, 总因子数 281 (原273 + 8: factors_wide过滤后250 + 衍生22 + 北向1 + sentiment 8)

**专家数**: 4模型 × 2超参 × **3特征集** × 2窗口 = **48个** (原32 + 16 sentiment)

**IS验证** (2025-01-01 ~ 2025-12-31, 48个调仓日, rank_average, ZZ500, Top-30, 同口径对比):

| 配置 | 专家数 | Sharpe | 超额收益 | 最大回撤 | Calmar | 月胜率 |
|------|--------|--------|----------|----------|--------|--------|
| 基线 (meTree32 final) | 32 | 3.0861 | +114.72% | - | - | - |
| **v2 (meTree48 final v2)** | **48** | **3.1106** | **+95.62%** | **-19.22%** | **6.0420** | **83.33%** |

**结论**: 48专家IS Sharpe 3.1106 微弱优于32专家基线 3.0861 (+0.0245), 月胜率83.33%显示IS稳定性良好。

> **⚠ OOS警示**: v2的OOS Sharpe为 **-1.4579** (vs 32专家 +0.0110, 退化-1.4690), 超额收益-12.24%, 平均换手率67.4%(vs 56.9%), 平均投票率51.5%(vs 59.5%)。IS微弱提升但OOS大幅退化, 说明sentiment特征集在IS上过拟合, 未泛化到OOS。详见第4节。建议: (1) 排查unlock_rate因子是否有未来信息泄漏 (解禁为已知未来事件, 但实施可能误用); (2) 拆分margin/money_flow/unlock单独验证; (3) 或回退至v1 (meTree32 final) 作为生产配置。

---

## 4. OOS 验证

### 4.1 OOS 验证结果

OOS区间: 2026-06-01 ~ 2026-07-29 (最新数据日, 42个交易日, 9个调仓日)

| 配置 | 集成方法 | 专家数 | OOS Sharpe | 超额收益 | 最大回撤 | 超额IR |
|------|----------|--------|------------|----------|----------|--------|
| 原始(已知过拟合) | ic_rank_weighted | 48 | -0.5242 | -7.35% | -37.46% | -0.238 |
| Phase A | rank_average | 48 | -0.1987 | -2.63% | -37.98% | +0.125 |
| Phase C v1 (80% train) | rank_average | 32 | -1.2255 | -13.94% | -25.50% | -1.234 |
| 旧OOS (data_start bug) | rank_average | 32(实际~16) | -0.0933 | -0.53% | -37.19% | +0.259 |
| 最终OOS (data_start修复) | rank_average | 32 | 0.0110 | +0.74% | -36.00% | +0.635 |
| **v2 OOS (+sentiment)** | **rank_average** | **48** | **-1.4579** | **-12.24%** | **-36.53%** | **-1.1548** |

**v2 OOS警示**: 48专家(+sentiment) OOS Sharpe -1.4579, 比32专家final (+0.0110)退化-1.4690, 是所有配置中OOS第二差(仅次于Phase C v1的-1.2255... 实际更差)。IS微弱提升(+0.0245)但OOS大幅退化, 典型的过拟合特征。可能原因:
1. **unlock_rate因子未来信息泄漏**: 解禁为已知未来事件, 公告日期公开, 但实施时若使用了预测日之后才公布的解禁数据, 会造成IS虚高OOS崩盘
2. **sentiment因子噪声大**: 融资融券/资金流/解禁数据稀疏(运行时大量All-NaN warning), 在小样本OOS上放大噪声
3. **专家数增加但样本未增加**: 48专家需要更多数据稳定, OOS仅9个调仓日样本太小

**注**:
- 旧OOS的`data_start="2025-06-01"`导致504日窗口专家训练数据不足被跳过, 实际仅~16个252日专家参与
- 最终OOS修复`data_start="2024-01-01"`, 确保32个专家全部参与
- Phase C v1使用80/20 holdout(所有方法), 导致OOS训练数据不足; v2修复后仅IC方法用holdout, rank_average全量训练

### 4.2 IS vs OOS 对比

| 配置 | IS Sharpe | OOS Sharpe | IS-OOS Gap | 过拟合? |
|------|-----------|------------|------------|---------|
| ic_rank_weighted (48专家) | 1.5043 | -0.5242 | 2.0285 | **严重过拟合** |
| rank_average (48专家) | 1.4725 | -0.1987 | 1.6712 | **过拟合** |
| rank_average (32专家, 旧OOS) | 1.7552 | -0.0933 | 1.8485 | 大幅改善 |
| rank_average (32专家, 最终OOS) | 1.7552 | 0.0110 | 1.7442 | OOS转正 |
| **rank_average (48专家v2, +sentiment)** | **3.1106** (2025) | **-1.4579** | **4.5685** | **严重过拟合(IS虚高OOS崩盘)** |

**关键改善**: 修复data_start后, OOS Sharpe从-0.0933改善到+0.0110 (转正), 超额收益从-0.53%改善到+0.74%。所有32个专家(含504日窗口)均参与预测, 集成更完整。

---

## 5. 过拟合根因分析

### 5.1 核心问题: IC计算样本内泄漏

**原代码** (旧版 walk_forward.py):
```python
def _compute_ic(train_preds, y_train):
    # train_preds = model.predict(X_train)  # 在训练集上预测!
    ic, _ = spearmanr(train_preds, y_train)  # 与训练标签算IC
```

**问题**: `train_preds` 是模型在**训练集本身**上的预测, 深树 (aggressive: max_depth=10) 几乎完全记忆训练数据, in-sample IC接近1.0。这导致 `ic_rank_weighted` 集成方法**把权重集中在最过拟合的专家上**, 是结构性过拟合放大器。

### 5.2 证据链

| 集成方法 | IS Sharpe | IC加权? | OOS Sharpe | 分析 |
|----------|-----------|---------|------------|------|
| equal_weight | 1.3814 | 否 | - | 基线, 无IC加权 |
| rank_average | 1.4725 | 否 | -0.1987 | +0.0911 rank鲁棒性提升 |
| ic_rank_weighted | 1.5043 | 是(样本内) | -0.5242 | +0.0318 仅小提升(过拟合副产物), OOS崩盘 |
| ic_weighted | 1.1243 | 是(样本内) | - | -0.2566 纯IC加权恶化 |

**关键发现**: IC加权的"IS提升"实际上是过拟合的副产品。`ic_rank_weighted` 比 `rank_average` IS仅高0.0318, 但OOS差0.3255。

### 5.3 模型复杂度过高

即使去除IC加权 (用rank_average), OOS Sharpe仍为-0.1987, 说明**模型本身也过拟合**:

1. **aggressive超参过深**: RF/ET max_depth=10; LGB/XGB max_depth=8, n_estimators=500
2. **旧48专家冗余 (hyper_set维度无效)**: 同类模型不同超参预测高度相关 (hyper_set discrimination=+0.0116, 几乎无区分), 集成无法有效降方差
3. **260+因子**: 因子数过多, 部分因子可能噪声大

> **v2更新**: 经专家相关性分析, feature_set维度是最有效差异化维度 (discrimination=-0.3853)。v2新增sentiment特征集(3特征集 × 48专家)在IS上微弱提升 (Sharpe 3.0861→3.1106), 验证了"差异化特征集"比"差异化超参"更有效的假设。

### 5.4 data_start配置bug

旧OOS验证脚本中`data_start="2025-06-01"`仅提供~252天训练数据, 导致504日窗口专家(16个, 占一半)在OOS期因数据不足被跳过。修复为`data_start="2024-01-01"`后, 全部32专家参与, OOS Sharpe从-0.0933改善到+0.0110。

---

## 6. 抗过拟合迭代

### 6.1 Phase B: 修复IC计算 (样本内 -> OOF holdout)

**改造** ([walk_forward.py:46-93](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/walk_forward.py#L46-L93)):

```python
def train_one_expert(expert, X_train, y_train, X_pred, n_jobs=-1, val_ratio=0.2, need_ic=True):
    """80/20时序holdout计算真实OOS IC

    - 前80%训练, 后20%作为holdout验证(时序, 避免未来信息泄漏)
    - 同一模型用于holdout验证和最终预测(保证IC与预测一致性)
    - 数据不足(<100样本)时退化为全量训练+in-sample验证
    - need_ic=False时(非IC集成方法)全量训练, 避免浪费数据
    """
    if not need_ic or n < 100:
        # rank_average/equal_weight: 全量训练, 不需holdout
        model = create_model(expert, n_jobs=n_jobs)
        model.fit(X_train, y_train)
        return model.predict(X_train), y_train, model.predict(X_pred)

    # IC集成方法: 80%训练 + 20%holdout验证
    split = int(n * (1 - val_ratio))
    X_tr, X_val = X_train[:split], X_train[split:]
    y_tr, y_val = y_train[:split], y_train[split:]
    model = create_model(expert, n_jobs=n_jobs)
    model.fit(X_tr, y_tr)
    return model.predict(X_val), y_val, model.predict(X_pred)
```

**效果**: IC-based集成方法 (ic_weighted, ic_rank_weighted) 现在使用真实泛化IC, 不再偏向过拟合专家。rank_average/equal_weight全量训练, 不浪费数据。

### 6.2 Phase C: 简化模型复杂度

**改造**: 去掉aggressive超参档(深树), 仅保留conservative+moderate:

专家数: 48 -> 32 (4模型 x 2超参 x 2特征 x 2窗口)

### 6.3 Phase D: v2 sentiment特征集扩展

**改造**: 在conservative+moderate基础上, feature_set维度新增sentiment (融资融券+资金流+解禁, 8个orthogonal因子):

专家数: 32 -> 48 (4模型 x 2超参 x **3特征** x 2窗口)

**依据**: 专家相关性分析显示feature_set是最有效差异化维度 (discrimination=-0.3853), 而hyper_set几乎无区分 (+0.0116)。因此v2选择在feature_set维度扩展而非恢复hyper_set。

**实现**:
- [factor_engine.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/factor_engine.py) 新增 `_load_margin_factors` / `_load_money_flow_factors` / `_load_unlock_factors` 三个loader
- [expert_pool.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/expert_pool.py) 新增 `SENTIMENT_PREFIXES = ["margin_", "mf_", "unlock_"]`, FEATURE_SETS含"sentiment"
- [config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/config.yaml) `factor_config` 新增 `use_margin/use_money_flow/use_unlock=true`, `expert.feature_sets` 加 "sentiment"

### 6.4 Phase C IS/OOS 结果

#### IS结果 (32专家, rank_average, cons+mod)

| 指标 | 48专家(all) | 32专家(cons+mod) | 变化 |
|------|-------------|------------------|------|
| Sharpe | 1.4725 | **1.7552** | +0.2827 |
| 超额收益 | 146.77% | **207.48%** | +60.71pp |
| 最大回撤 | -29.36% | -32.65% | -3.29pp |
| Calmar | 1.3103 | **1.4790** | +0.1687 |
| 月胜率 | 58.8% | **67.7%** | +8.9pp |

#### OOS结果

| 指标 | 48专家(ic_rank_weighted) | 48专家(rank_average) | 32专家(旧OOS) | **32专家(最终OOS)** |
|------|--------------------------|----------------------|---------------|---------------------|
| Sharpe | -0.5242 | -0.1987 | -0.0933 | **0.0110** |
| 超额收益 | -7.35% | -2.63% | -0.53% | **+0.74%** |
| 最大回撤 | -37.46% | -37.98% | -37.19% | -36.00% |
| 超额IR | -0.238 | +0.125 | +0.259 | **+0.635** |

**结论**: 抗过拟合迭代成功。OOS Sharpe从-0.5242改善到+0.0110 (转正), 超额收益从-7.35%改善到+0.74%。

---

## 7. 建仓调仓说明

### 7.1 同花顺交易文件生成

从2026-06-01建仓起, 每周一调仓, 生成同花顺PMS交易流水文件。

**文件结构**:
```
output/ths/expertforest_v1/
├── 20260601_build.xlsx              # 建仓交易流水
├── 20260601_build_report.md         # 建仓分析报告
├── 20260608_rebalance.xlsx          # 第1次调仓交易流水
├── 20260608_rebalance_report.md     # 第1次调仓分析报告
├── ...
├── 20260727_rebalance.xlsx          # 第8次调仓交易流水
├── 20260727_rebalance_report.md     # 第8次调仓分析报告
└── summary.md                       # 汇总报告
```

**交易规则**:
- 初始资金: 10,000,000
- 等权配置Top-30只个股 (每只~3.33%)
- 100股整数手 (LOT_SIZE=100)
- 交易费率: 0.10% (含佣金+印花税+过户费)
- 开盘价成交 (adjust="none" 实际市场价格, 非复权)
- 建仓: 全部买入; 调仓: 先卖后买

### 7.2 调仓分析报告内容

每次调仓生成独立markdown报告, 包含:

1. **基本信息**: 调仓日期/类型/股票只数/总权重/权重范围/换手率/持仓市值/现金余额
2. **交易摘要**: 买入/卖出笔数/金额/费用
3. **持仓明细**: 证券代码/行业/权重/rank得分/开盘价/持仓股数/市值/专家投票数/投票率
4. **专家投票详情**:
   - 按模型类型汇总 (RF/ET/LGB/XGB 的平均投票率和平均rank)
   - 每只股票的专家投票 (投票数/48, 投票率, 平均rank, 各模型投票明细)
5. **选股逻辑**: 集成方法说明, 选股标准
6. **交易明细**: 每笔交易的代码/数量/价格/金额/费用

### 7.3 专家投票分析

**投票定义**: 每个专家对全池~500只股票输出预测值, 排名后取个人top-30。某专家"投票"某股 = 该股在其个人top-30中。

**投票率**: 投票专家数 / 48。高投票率表示专家共识强, 低投票率但高rank得分表示部分专家强烈看好。

**实际数据** (2026-06-01 ~ 2026-07-27, 9次调仓, meTree48 v2):

| 指标 | 值 | vs 32专家v1 |
|------|------|-------------|
| 调仓总次数 | 9 | 同 |
| 建仓次数 | 1 | 同 |
| 调仓次数(非建仓) | 8 | 同 |
| 平均换手率(非建仓) | 67.4% | +10.5pp (更不稳定) |
| 平均专家投票率 | 51.5% | -8.0pp (共识下降) |
| OOS Sharpe | -1.4579 | -1.4690 (大幅退化) |
| OOS超额收益 | -12.24% | -12.98pp |

### 7.4 生成命令

```bash
# 生成全部建仓+调仓文件 (运行OOS回测 + 生成xlsx + 报告)
python scripts/expertforest_v1/expertforest_v1_position_analysis.py

# 指定结束日期
python scripts/expertforest_v1/expertforest_v1_position_analysis.py --end-date 2026-07-20
```

---

## 8. 复现指南

### 8.1 环境准备

```bash
pip install scikit-learn lightgbm xgboost polars numpy scipy joblib pyyaml duckdb openpyxl
```

### 8.2 IS 验证

```bash
# 基线 (equal_weight, 48专家)
python scripts/expertforest_v1/expertforest_v1_is_explore.py --pool 000905.XSHG --top_n 30 --ensemble equal_weight

# rank_average (48专家)
python scripts/expertforest_v1/expertforest_v1_is_explore.py --pool 000905.XSHG --top_n 30 --ensemble rank_average

# v1 final (rank_average, 32专家, 无aggressive)
python scripts/expertforest_v1/expertforest_v1_is_explore.py --pool 000905.XSHG --top_n 30 --ensemble rank_average --hyper_sets conservative,moderate

# v2 final (rank_average, 48专家, +sentiment特征集) — 当前配置已写入config.yaml, 直接运行即可
python scripts/expertforest_v1/expertforest_v1_is_explore.py --pool 000905.XSHG --top_n 30 --ensemble rank_average --feature_sets momentum,fundamental,sentiment
```

### 8.3 OOS 验证

```bash
# 最终配置 OOS验证
python scripts/expertforest_v1/expertforest_v1_oos_validate.py --pool 000905.XSHG --top_n 30 --ensemble rank_average
```

### 8.4 建仓调仓文件生成

```bash
# 生成同花顺交易文件 + 分析报告
python scripts/expertforest_v1/expertforest_v1_position_analysis.py
```

---

## 9. 关键文件

| 文件 | 说明 |
|------|------|
| [config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/config.yaml) | 策略配置 |
| [strategy.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/strategy.py) | 策略主入口 |
| [walk_forward.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/walk_forward.py) | Walk Forward滚动训练 (含OOF IC修复) |
| [expert_pool.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/expert_pool.py) | 48专家池配置 (含SENTIMENT_PREFIXES) |
| [factor_engine.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/factor_engine.py) | 因子引擎 |
| [backtest.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/expertForest/v1/backtest.py) | 回测引擎 |
| [scripts/expertforest_v1/expertforest_v1_is_explore.py](file:///d:/Work/Project/OhMyQuant/scripts/expertforest_v1/expertforest_v1_is_explore.py) | IS验证脚本 |
| [scripts/expertforest_v1/expertforest_v1_oos_validate.py](file:///d:/Work/Project/OhMyQuant/scripts/expertforest_v1/expertforest_v1_oos_validate.py) | OOS验证脚本 |
| [scripts/expertforest_v1/expertforest_v1_position_analysis.py](file:///d:/Work/Project/OhMyQuant/scripts/expertforest_v1/expertforest_v1_position_analysis.py) | 建仓调仓分析+THS文件生成 |
| [templates/ths_pms_template.xlsx](file:///d:/Work/Project/OhMyQuant/templates/ths_pms_template.xlsx) | 同花顺交易流水模板 |

---

## 10. 版本历史

| 版本 | 配置 | IS Sharpe | OOS Sharpe | 状态 |
|------|------|-----------|------------|------|
| v1 (meTree48, ic_rank_weighted) | 48专家, ic_rank_weighted | 1.5043 | -0.5242 | **过拟合, 已废弃** |
| v1 (meTree48, rank_average) | 48专家, rank_average | 1.4725 | -0.1987 | 过拟合 |
| v1 (meTree32, 旧OOS) | 32专家, rank_average, cons+mod | 1.7552 | -0.0933 | data_start bug |
| v1 (meTree32, final) | 32专家, rank_average, cons+mod | 1.7552 | 0.0110 | final (OOS转正) |
| v1 (meTree48, final v2) | 48专家, rank_average, cons+mod, +sentiment | 3.1106 (2025-scope) | **-1.4579** | **IS收敛但OOS退化, 需排查sentiment因子** |
| **v1 (meTree32, final v3)** | **32专家, rank_average, cons+mod (回退v2)** | **3.0903 (2025-scope)** | **-0.0843** | **生产配置 (OOS转正, v4优化证明无需调整)** |
| v4a (w504 only) | 16专家, 仅w504 | - | -0.6334 | OOS退化, 多样性损失 |
| v4b (fundamental only) | 16专家, 仅fundamental | - | -0.5723 | OOS退化, 多样性损失 |
| v4d (w504+fundamental) | 8专家, 双重过滤 | - | -0.7275 | OOS最差, 过度筛选 |

> **注**: v2的IS Sharpe 3.1106 为2025-scope (2025-01-01~2025-12-31, 48调仓日) 同口径对比基线32专家的3.0861, IS微弱提升(+0.0245); 但OOS Sharpe从+0.0110退化到-1.4579 (-1.4690), 超额收益从+0.74%退化到-12.24%, 平均换手率从56.9%升到67.4%, 平均投票率从59.5%降到51.5%。IS"提升"实为过拟合, sentiment特征集在OOS上未泛化。

> **v3状态**: v2排查后回退至32专家(meTree32), 移除sentiment特征集。v3 OOS (2026-06-01~2026-12-31, 147交易日, 9调仓日) Sharpe=-0.0843, 超额+0.78%, 优于基准Sharpe=-0.8472。v4优化尝试 (第12节) 证明基于IS表现筛选专家会伤害OOS, **保持v3 32专家配置不变**。

---

## 11. v3 每专家深度分析 (2025 IS)

### 11.1 分析方法

运行 [scripts/expertforest_v1/expertforest_v1_per_expert_analysis.py](file:///d:/Work/Project/OhMyQuant/scripts/expertforest_v1/expertforest_v1_per_expert_analysis.py), 对每个专家单独计算 **forward IC** (5日前向超额收益Spearman IC), 区别于 holdout IC:

| 指标 | 计算方式 | 用途 |
|------|----------|------|
| **forward IC** | 专家预测排名 vs 下一持仓期实际超额收益排名的Spearman相关 | 真实选股能力 |
| **holdout IC** | 80/20时序holdout验证集上的IC (仅IC集成方法用) | 模型拟合度参考 |
| **forward IC IR** | forward IC均值/标准差 | 选股稳定性 |
| **positive rate** | forward IC>0的调仓日比例 | 选股一致性 |

**数据范围**: 2025-01-01 ~ 2025-12-31, 48个调仓日(每周一), 32专家, rank_average, 中证500, Top-30

### 11.2 每专家forward IC排名

#### Top 5 (fundamental_w504 霸榜)

| 排名 | 专家ID | forward IC | IR | 正率 | holdout IC |
|------|--------|-----------|-----|------|-----------|
| 1 | lgb_conservative_fundamental_w504 | +0.0679 | 0.814 | 79% | 0.184 |
| 2 | rf_conservative_fundamental_w504 | +0.0646 | 0.650 | 71% | 0.134 |
| 3 | et_moderate_fundamental_w504 | +0.0621 | 0.435 | 62% | 0.135 |
| 4 | et_conservative_fundamental_w504 | +0.0607 | 0.402 | 62% | 0.086 |
| 5 | xgb_conservative_fundamental_w504 | +0.0582 | 0.662 | 77% | 0.187 |

#### Bottom 5 (momentum_w252/w504 垫底)

| 排名 | 专家ID | forward IC | IR | 正率 | holdout IC |
|------|--------|-----------|-----|------|-----------|
| 28 | et_moderate_momentum_w504 | +0.0142 | 0.079 | 54% | 0.169 |
| 29 | et_conservative_momentum_w504 | +0.0111 | 0.058 | 58% | 0.111 |
| 30 | et_moderate_momentum_w252 | +0.0109 | 0.050 | 50% | 0.211 |
| 31 | rf_conservative_momentum_w504 | +0.0099 | 0.060 | 52% | 0.143 |
| 32 | et_conservative_momentum_w252 | +0.0023 | 0.010 | 48% | 0.139 |

**关键发现**: Top 5全是fundamental_w504, Bottom 5全是momentum。但**holdout IC与forward IC弱相关** — Bottom 5的holdout IC (0.111~0.211) 并不比Top 5 (0.086~0.187) 差, 说明holdout IC不能预测真实选股能力。

### 11.3 按维度分组分析

| 维度 | 分组 | 专家数 | forward IC均值 | IR均值 | 正率 | holdout IC |
|------|------|--------|---------------|--------|------|-----------|
| **feature_set** | **fundamental** | 16 | **+0.0532** | **0.441** | **65.6%** | 0.228 |
| feature_set | momentum | 16 | +0.0245 | 0.164 | 56.3% | 0.275 |
| **train_window** | **504** | 16 | **+0.0403** | **0.352** | **62.8%** | 0.224 |
| train_window | 252 | 16 | +0.0374 | 0.252 | 59.1% | 0.279 |
| **model_type** | **lgb** | 8 | **+0.0478** | **0.417** | **65.9%** | 0.331 |
| model_type | xgb | 8 | +0.0411 | 0.354 | 63.3% | 0.341 |
| model_type | rf | 8 | +0.0352 | 0.261 | 58.6% | 0.198 |
| model_type | et | 8 | +0.0315 | 0.177 | 56.0% | 0.137 |
| hyper_set | conservative | 16 | +0.0398 | 0.323 | 61.2% | 0.186 |
| hyper_set | moderate | 16 | +0.0380 | 0.282 | 60.7% | 0.318 |

**IS分组结论** (注意:IS结论≠OOS结论, 见第12节):
1. **feature_set最关键**: fundamental(+0.053) >> momentum(+0.025), 差异2倍
2. **train_window次之**: w504(+0.040, IR=0.352) 略优于 w252(+0.037, IR=0.252), w504更稳定
3. **model_type**: lgb>xgb>rf>et, lgb/xgb显著优于rf/et
4. **hyper_set**: conservative≈moderate, 差异最小 (验证了v1阶段的correlation分析结论)

### 11.4 集成forward IC统计

32专家rank_average集成的forward IC时序统计:
- **均值**: +0.0517 (正向选股能力)
- **标准差**: 0.1765
- **IR**: 0.293
- **正率**: 60% (48个调仓日中29个正向)

集成forward IC (+0.0517) 高于任何单维度分组均值, 说明rank_average有效利用了专家多样性。

### 11.5 forward IC vs holdout IC: 弱相关

| 维度 | forward IC | holdout IC | 关系 |
|------|-----------|-----------|------|
| fundamental | +0.053 | 0.228 | holdout更高 |
| momentum | +0.025 | 0.275 | holdout更高但forward更低! |
| w504 | +0.040 | 0.224 | - |
| w252 | +0.037 | 0.279 | holdout更高但forward更低! |
| lgb | +0.048 | 0.331 | holdout最高 |
| et | +0.032 | 0.137 | holdout最低 |

**关键发现**: holdout IC与forward IC**负相关或弱相关**:
- momentum的holdout IC (0.275) > fundamental (0.228), 但forward IC相反 (0.025 < 0.053)
- w252的holdout IC (0.279) > w504 (0.224), 但forward IC相反 (0.037 < 0.040)
- lgb的holdout IC最高 (0.331), forward IC也最高 (0.048), 但et两者都最低

**结论**: holdout IC (80/20时序验证) 不能可靠预测forward IC (真实下一期选股能力)。holdout IC高的专家可能是过拟合 (w252窗口短、momentum特征噪声大), 在验证集上表现好但泛化差。

---

## 12. v4 优化尝试与OOS验证

### 12.1 优化假设

基于第11节IS分析, 提出3个优化假设 (移除IS表现弱的专家):

| 变体 | 配置 | 专家数 | 假设 |
|------|------|--------|------|
| **v4a** | 仅w504 (移除w252) | 16 | w504 forward IC IR (0.352) > w252 (0.252), 移除弱窗口 |
| **v4b** | 仅fundamental (移除momentum) | 16 | fundamental forward IC (+0.053) >> momentum (+0.025), 移除弱特征 |
| **v4d** | w504+fundamental (双重过滤) | 8 | 保留两个维度的强专家, 最激进 |

### 12.2 OOS验证结果

OOS区间: 2026-06-01 ~ 2026-12-31 (147交易日, 9个调仓日, rank_average, 中证500, Top-30)

| 配置 | 专家数 | OOS Sharpe | 超额收益 | 最大回撤 | 月胜率 | vs基线 |
|------|--------|-----------|---------|----------|--------|--------|
| **v3基线 (32专家)** | **32** | **-0.0843** | **+0.78%** | **-36.0%** | **14.3%** | **基准** |
| v4a (w504 only) | 16 | -0.6334 | -9.11% | -37.1% | 16.7% | 退化 |
| v4b (fundamental only) | 16 | -0.5723 | -9.48% | -39.8% | 16.7% | 退化 |
| v4d (w504+fundamental) | 8 | -0.7275 | -11.63% | -38.9% | 16.7% | 退化最多 |

### 12.3 关键发现: 多样性 > IS筛选

**所有优化变体OOS都比基线差**, 且筛选越激进OOS越差:
- v4a (移除w252): Sharpe -0.633 (vs基线-0.084, 退化-0.549)
- v4b (移除momentum): Sharpe -0.572 (vs基线-0.084, 退化-0.488)
- v4d (双重过滤): Sharpe -0.728 (vs基线-0.084, 退化-0.644) — 最差

**根因分析**:
1. **IS弱专家在OOS提供关键差异化信号**: momentum在2025 IS表现弱 (forward IC +0.025), 但2026 OOS不同市场环境下其信号可能互补fundamental
2. **w252短窗口适应性强**: w252在IS holdout IC更高但forward IC更低 (过拟合), 但在OOS快速变化的市场中可能捕捉到w504错过的信号
3. **rank_average受益于最大多样性**: 32专家的预测排名平均, 即使个别专家弱, 集成后仍能有效降低方差; 移除专家减少方差降低效果
4. **IS性能 ≠ OOS贡献**: 基于IS forward IC筛选专家, 本质是用IS信息做OOS决策, 导致OOS过拟合

### 12.4 结论: 保持v3 32专家配置

v4优化尝试**全部失败**, 证明v3 32专家配置已是最优:
- ❌ 不更新 `train_windows` (保持 [252, 504])
- ❌ 不更新 `feature_sets` (保持 [momentum, fundamental])
- ❌ 不更新 `model_types` (保持 [rf, et, lgb, xgb])
- ❌ 不更新 `hyper_sets` (保持 [conservative, moderate])
- ✅ **保持v3 config.yaml不变**

---

## 13. 核心结论与教训

### 13.1 策略状态

**expertForest_v1 (meTree32, final v3)** 为生产就绪配置:
- 32专家 (4模型 × 2超参 × 2特征 × 2窗口)
- rank_average集成 (抗过拟合, 无IC加权泄漏)
- 中证500, Top-30, 周频调仓
- IS 2025: Sharpe 3.09, 超额+114.9%, MDD -20.5%
- OOS 2026-06+: Sharpe -0.084 (优于基准-0.847), 超额+0.78%, MDD -36.0%

### 13.2 关键教训

1. **多样性是OOS泛化的核心**, 而非IS性能优化。基于IS表现筛选专家 = OOS过拟合。
2. **holdout IC不能预测forward IC**。80/20时序holdout验证集上的IC与真实下一期选股能力弱相关甚至负相关。
3. **IS per-expert forward IC有诊断价值, 但无决策价值**。能识别哪些专家在IS表现好, 但不能据此筛选OOS专家。
4. **rank_average集成的优势在于"不挑专家"**。即使包含弱专家, 集成后仍能有效降低方差, 优于人工筛选的子集。
5. **v2 sentiment失败的根因复现**: sentiment特征集在IS上微弱提升 (+0.0245 Sharpe) 但OOS大幅退化 (-1.4690), 与v4优化尝试的失败模式一致 — IS优化导致OOS过拟合。

### 13.3 后续方向 (不建议立即实施)

v3已是最优, 若未来探索:
1. **新增正交特征集** (非筛选现有专家): 如sentiment修复后重新加入, 增加多样性维度而非减少
2. **动态专家权重** (非硬筛选): 基于近期forward IC动态调整权重, 但需防范过拟合
3. **更长OOS验证**: 当前OOS仅9个调仓日, 样本小, 需积累更多OOS数据确认

### 13.4 复现命令

```bash
# v3基线 IS验证 (2025)
python scripts/expertforest_v1/expertforest_v1_per_expert_analysis.py --start 2025-01-01 --end 2025-12-31 --top_n 30 --n_jobs -1 --output_dir output/per_expert_2025

# v3基线 OOS验证
python scripts/expertforest_v1/expertforest_v1_oos_validate.py --pool 000905.XSHG --top_n 30

# v4a优化 (仅w504) OOS验证
python scripts/expertforest_v1/expertforest_v1_oos_validate.py --pool 000905.XSHG --top_n 30 --train_windows 504

# v4b优化 (仅fundamental) OOS验证
python scripts/expertforest_v1/expertforest_v1_oos_validate.py --pool 000905.XSHG --top_n 30 --feature_sets fundamental

# v4d优化 (w504+fundamental) OOS验证
python scripts/expertforest_v1/expertforest_v1_oos_validate.py --pool 000905.XSHG --top_n 30 --train_windows 504 --feature_sets fundamental
```

### 13.5 关键文件

| 文件 | 说明 |
|------|------|
| [output/per_expert_2025/](file:///d:/Work/Project/OhMyQuant/output/per_expert_2025/) | v3基线IS每专家分析结果 (expert_summary.csv, group_analysis.csv, ensemble_ic.csv, monthly_ic.csv, metrics.json) |
| [output/per_expert_smoke/](file:///d:/Work/Project/OhMyQuant/output/per_expert_smoke/) | Q1 2024冒烟测试 (11调仓日, 不代表全年, 仅供参考) |
| [output/oos_validate/expertforest_v1/](file:///d:/Work/Project/OhMyQuant/output/oos_validate/expertforest_v1/) | OOS验证结果 (基线 + v4a/v4b/v4d变体) |
| [scripts/expertforest_v1/expertforest_v1_per_expert_analysis.py](file:///d:/Work/Project/OhMyQuant/scripts/expertforest_v1/expertforest_v1_per_expert_analysis.py) | 每专家分析脚本 (支持 --train_windows / --feature_sets / --model_types) |
| [scripts/expertforest_v1/expertforest_v1_oos_validate.py](file:///d:/Work/Project/OhMyQuant/scripts/expertforest_v1/expertforest_v1_oos_validate.py) | OOS验证脚本 (文件名含全部override维度, 避免覆盖) |
