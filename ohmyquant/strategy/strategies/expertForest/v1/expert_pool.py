"""专家模型池：32个差异化专家树配置

4模型类型 × 2超参组合 × 2特征集 × 2训练窗口 = 32个专家

模型类型:
  - rf  (RandomForest):     Bootstrap采样 + 信息增益分裂
  - et  (ExtraTrees):       全样本 + 随机阈值分裂
  - lgb (LightGBM):         直方图加速 + 叶子优先生长
  - xgb (XGBoost):          预排序 + 深度优先生长

多样性保证:
  1. 模型结构差异 (分裂策略/生长方向/采样方式)
  2. 超参差异 (conservative 浅树 / moderate 中树)
  3. 特征集差异 (动量信号 vs 基本面信号)
  4. 训练窗口差异 (1年适应 vs 2年稳健)
  5. 随机种子差异 (0-31)

注: aggressive 深树(max_depth=10)已移除 — IS迭代证明其in-sample IC虚高导致过拟合,
    去掉后IS Sharpe反而从1.4725提升到1.7552(深树在添加噪声而非信号)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ============================================================
# 超参预设 (conservative + moderate, 无aggressive深树)
# ============================================================

HYPER_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "rf": {
        "conservative": {"n_estimators": 150, "max_depth": 6, "min_samples_leaf": 40, "max_features": "sqrt"},
        "moderate":     {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 20, "max_features": "sqrt"},
    },
    "et": {
        "conservative": {"n_estimators": 150, "max_depth": 6, "min_samples_leaf": 40, "max_features": "sqrt"},
        "moderate":     {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 20, "max_features": "sqrt"},
    },
    "lgb": {
        "conservative": {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05, "num_leaves": 15, "subsample": 0.8, "colsample_bytree": 0.8},
        "moderate":     {"n_estimators": 350, "max_depth": 6, "learning_rate": 0.04, "num_leaves": 47, "subsample": 0.8, "colsample_bytree": 0.8},
    },
    "xgb": {
        "conservative": {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8},
        "moderate":     {"n_estimators": 350, "max_depth": 6, "learning_rate": 0.04, "subsample": 0.8, "colsample_bytree": 0.8},
    },
}

# ============================================================
# 特征集定义（因子名前缀匹配）
# ============================================================

# 动量类因子前缀（价格动量+量价+技术指标+衍生因子）
MOMENTUM_PREFIXES = [
    "Price", "ROC", "MOM", "momentum", "DAVOL", "money_flow",
    "RSI", "CCI", "MACD", "BIAS", "KDJ", "VOL", "ATR",
    "turnover", "Skewness", "Kurtosis", "VWAP",
    "hk_hold",  # 北向资金(动量信号)
    "drv_",     # 衍生因子(均线/动量/波动/成交量比/反转)
]

# 基本面类因子前缀（估值+质量+财务+规模）
FUNDAMENTAL_PREFIXES = [
    "earnings_to_price", "book_to_price", "roe", "roa", "net_profit",
    "gross_income", "debt_to", "current_ratio", "inventory_turnover",
    "ln_market_cap", "circulating", "pe_", "pb_", "ps_", "pcf_",
    "dividend", "beta", "raw_beta", "residual_volatility",
]

# 情绪/卖压类因子前缀 (融资融券+大单资金流+解禁, 与factors_wide无重叠的orthogonal信号)
SENTIMENT_PREFIXES = [
    "margin_",  # 融资融券余额变化 (杠杆做多/做空情绪)
    "mf_",      # 大单/超大单净流入 (主力资金动向)
    "unlock_",  # 解禁压力 (已知未来事件, 卖压信号)
]

FEATURE_SETS = {
    "momentum": MOMENTUM_PREFIXES,
    "fundamental": FUNDAMENTAL_PREFIXES,
    "sentiment": SENTIMENT_PREFIXES,
    "combined": MOMENTUM_PREFIXES + FUNDAMENTAL_PREFIXES + SENTIMENT_PREFIXES,
}


@dataclass
class ExpertConfig:
    """单个专家配置"""
    expert_id: str
    model_type: str          # rf / et / lgb / xgb
    hyper_set: str           # conservative / moderate / aggressive
    hyper_params: dict       # 具体超参
    feature_set: str         # momentum / fundamental
    feature_prefixes: list[str]
    train_window: int        # 252 / 504
    random_state: int


def build_expert_pool(
    model_types: list[str] | None = None,
    hyper_sets: list[str] | None = None,
    feature_sets: list[str] | None = None,
    train_windows: list[int] | None = None,
) -> list[ExpertConfig]:
    """构建专家池

    默认: 4×2×2×2 = 32个专家 (无aggressive深树)
    """
    model_types = model_types or ["rf", "et", "lgb", "xgb"]
    hyper_sets = hyper_sets or ["conservative", "moderate"]
    feature_sets = feature_sets or ["momentum", "fundamental"]
    train_windows = train_windows or [252, 504]

    pool: list[ExpertConfig] = []
    idx = 0
    for mt in model_types:
        for hs in hyper_sets:
            for fs in feature_sets:
                for tw in train_windows:
                    pool.append(ExpertConfig(
                        expert_id=f"{mt}_{hs}_{fs}_w{tw}",
                        model_type=mt,
                        hyper_set=hs,
                        hyper_params={**HYPER_PRESETS[mt][hs], "random_state": idx},
                        feature_set=fs,
                        feature_prefixes=FEATURE_SETS[fs],
                        train_window=tw,
                        random_state=idx,
                    ))
                    idx += 1
    return pool


def filter_features(factor_names: list[str], prefixes: list[str]) -> list[str]:
    """根据前缀列表筛选因子名"""
    selected = []
    for fn in factor_names:
        if any(fn.startswith(p) or fn == p for p in prefixes):
            selected.append(fn)
    return selected


def create_model(expert: ExpertConfig, n_jobs: int = -1):
    """根据专家配置创建模型实例

    Args:
        expert: 专家配置
        n_jobs: RF/ET使用的核心数(-1=全部, 并行运行时设为具体值如8)
    """
    params = {k: v for k, v in expert.hyper_params.items() if k != "random_state"}
    rs = expert.hyper_params.get("random_state", 42)

    if expert.model_type == "rf":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(random_state=rs, n_jobs=n_jobs, **params)
    elif expert.model_type == "et":
        from sklearn.ensemble import ExtraTreesRegressor
        return ExtraTreesRegressor(random_state=rs, n_jobs=n_jobs, **params)
    elif expert.model_type == "lgb":
        from lightgbm import LGBMRegressor
        return LGBMRegressor(random_state=rs, n_jobs=1, verbose=-1, **params)
    elif expert.model_type == "xgb":
        from xgboost import XGBRegressor
        return XGBRegressor(random_state=rs, n_jobs=1, verbosity=0, **params)
    else:
        raise ValueError(f"未知模型类型: {expert.model_type}")
