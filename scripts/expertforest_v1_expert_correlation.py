"""expertForest_v1 专家行为相关性 & 选股重叠度分析

目标: 检查32个专家是否存在行为重合/冗余, 为专家池优化提供依据。

分析内容:
  1. 专家预测值相关性矩阵 (32×32 Spearman相关性)
     - 高相关(>0.95)的专家对 = 行为高度重合 = 冗余候选
  2. 选股重叠度矩阵 (32×32 Jaccard@TopN)
     - 高重叠(>0.85)的专家对 = 选股几乎一致 = 冗余候选
  3. 专家IC分布 (各专家预测能力对比)
  4. 按维度分组分析 (model_type / hyper_set / feature_set / train_window)
     - 同维度内 vs 跨维度 的平均相关性, 判断哪个维度区分度低

输出:
  output/expert_analysis/correlation_report.md     分析报告
  output/expert_analysis/expert_corr_matrix.png    相关性热力图
  output/expert_analysis/expert_overlap_matrix.png 重叠度热力图
  output/expert_analysis/expert_predictions_cache.json  缓存(避免重复跑回测)

用法:
  # 默认: 2024-2025 IS区间分析 (约1.5h)
  python scripts/expertforest_v1_expert_correlation.py

  # 快速模式: 仅2025下半年 (~30min)
  python scripts/expertforest_v1_expert_correlation.py --short

  # 复用缓存(已跑过回测, 只重算分析)
  python scripts/expertforest_v1_expert_correlation.py --use-cache

  # 自定义区间
  python scripts/expertforest_v1_expert_correlation.py --start 2024-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy.stats import rankdata, spearmanr

from ohmyquant.strategy import StrategyRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output" / "expert_analysis"
CACHE_FILE = OUTPUT_DIR / "expert_predictions_cache.json"
POOL_INDEX = "000905.XSHG"
TOP_N = 30


# ====================================================================
# 1. 运行回测并缓存专家预测
# ====================================================================

def run_backtest_and_cache(start: str, end: str, data_start: str) -> dict:
    """运行IS回测, 返回简化的expert_predictions缓存

    缓存结构:
    {
        "config": {start, end, pool, top_n},
        "rebalance_dates": [
            {
                "date": "2024-01-08",
                "selected_codes": [...],
                "predictions": {code: score, ...},  # 集成后
                "expert_predictions": [
                    {"expert_id": "rf_cons_momentum_w252",
                     "model_type": "rf",
                     "ic": 0.05,
                     "predictions": {code: pred, ...}},
                    ...
                ]
            },
            ...
        ]
    }
    """
    print(f"\n运行 expertForest_v1 IS回测: {start} -> {end}")
    print(f"  数据起始: {data_start}")
    print(f"  股票池: {POOL_INDEX} | Top-{TOP_N} | rank_average")

    config_override = {
        "pools": {"stocks": {"index": POOL_INDEX}},
        "selection": {"top_n": TOP_N},
        "backtest": {
            "start_date": start,
            "end_date": end,
            "data_start_date": data_start,
        },
        "ensemble": {"method": "rank_average"},
    }

    t0 = time.time()
    strategy = StrategyRegistry.create("expertForest", "v1", config_override)
    result = strategy.run()
    elapsed = time.time() - t0
    print(f"\n回测耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    wf_results = result.get("wf_results", [])
    metrics = result.get("metrics", {})

    # 简化缓存: 只保留必要字段, 避免JSON过大
    cache = {
        "config": {
            "start": start, "end": end, "data_start": data_start,
            "pool": POOL_INDEX, "top_n": TOP_N,
            "ensemble": "rank_average",
        },
        "metrics": metrics,
        "elapsed_sec": elapsed,
        "rebalance_dates": [],
    }

    for r in wf_results:
        if not r.get("expert_predictions"):
            continue
        entry = {
            "date": r["date"],
            "selected_codes": r.get("selected_codes", []),
            "predictions": r.get("predictions", {}),
            "expert_predictions": [
                {
                    "expert_id": e["expert_id"],
                    "model_type": e["model_type"],
                    "ic": e.get("ic", 0.0),
                    "predictions": e.get("predictions", {}),
                }
                for e in r["expert_predictions"]
            ],
        }
        cache["rebalance_dates"].append(entry)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"缓存已保存: {CACHE_FILE} ({len(cache['rebalance_dates'])} 个调仓日)")
    print(f"OOS Sharpe: {metrics.get('sharpe', 0):.4f}")

    return cache


# ====================================================================
# 2. 相关性分析
# ====================================================================

def parse_expert_id(expert_id: str) -> dict:
    """解析 expert_id (格式: {model_type}_{hyper_set}_{feature_set}_w{window})"""
    parts = expert_id.split("_")
    if len(parts) < 4:
        return {"model_type": "?", "hyper_set": "?", "feature_set": "?", "train_window": 0}
    return {
        "model_type": parts[0],
        "hyper_set": parts[1],
        "feature_set": parts[2],
        "train_window": int(parts[3].lstrip("w")),
    }


def compute_expert_correlation(cache: dict) -> tuple[np.ndarray, list[str], list[dict]]:
    """计算专家预测值相关性矩阵

    方法: 对每个调仓日, 取每个专家对全池股票的预测值, 转为rank(消除scale差异),
         然后跨所有调仓日拼接, 计算专家两两Spearman相关性。

    Returns:
        corr_matrix: (N, N) 相关性矩阵
        expert_ids: 专家ID列表
        expert_meta: 每个专家的元信息 (model_type, hyper_set, ...)
    """
    rebalance_dates = cache["rebalance_dates"]
    if not rebalance_dates:
        raise RuntimeError("无调仓日数据")

    # 收集所有专家ID (以第一个调仓日为准, 假设专家池一致)
    expert_ids = [e["expert_id"] for e in rebalance_dates[0]["expert_predictions"]]
    n_experts = len(expert_ids)
    print(f"\n计算专家预测相关性: {n_experts} 专家 × {len(rebalance_dates)} 调仓日")

    # 对每个调仓日, 收集所有专家对相同股票集合的rank预测
    # 拼接成大矩阵: 每列=一个专家, 每行=某调仓日的某只股票
    all_rank_arrays = []  # list of (n_stocks_in_day, n_experts) arrays
    for entry in rebalance_dates:
        expert_preds = entry["expert_predictions"]
        if len(expert_preds) != n_experts:
            continue

        # 取所有专家预测股票的并集
        all_codes = set()
        for e in expert_preds:
            all_codes.update(e["predictions"].keys())
        all_codes = sorted(all_codes)
        if len(all_codes) < 5:
            continue

        # 构建矩阵 (n_codes, n_experts), 每列是该专家的预测rank
        rank_matrix = np.zeros((len(all_codes), n_experts))
        code_to_idx = {c: i for i, c in enumerate(all_codes)}
        for j, e in enumerate(expert_preds):
            preds = e["predictions"]
            values = np.array([preds.get(c, np.nan) for c in all_codes], dtype=float)
            valid = ~np.isnan(values)
            if valid.sum() < 2:
                continue
            # rank归一化到[0,1], 与集成方法一致
            ranks = np.full_like(values, np.nan)
            ranks[valid] = rankdata(values[valid]) / valid.sum()
            rank_matrix[:, j] = ranks

        all_rank_arrays.append(rank_matrix)

    if not all_rank_arrays:
        raise RuntimeError("无有效数据计算相关性")

    # 拼接所有调仓日
    big_matrix = np.vstack(all_rank_arrays)  # (total_rows, n_experts)
    print(f"  拼接矩阵: {big_matrix.shape}")

    # 计算Spearman相关性 (rank已应用, 直接用Pearson on ranks = Spearman)
    # 处理NaN: 用np.corrcoef逐对计算
    corr_matrix = np.zeros((n_experts, n_experts))
    for i in range(n_experts):
        for j in range(n_experts):
            if i == j:
                corr_matrix[i, j] = 1.0
                continue
            x = big_matrix[:, i]
            y = big_matrix[:, j]
            valid = ~np.isnan(x) & ~np.isnan(y)
            if valid.sum() < 10:
                corr_matrix[i, j] = 0.0
                continue
            c, _ = spearmanr(x[valid], y[valid])
            corr_matrix[i, j] = 0.0 if np.isnan(c) else c

    # 专家元信息
    expert_meta = [parse_expert_id(eid) for eid in expert_ids]

    return corr_matrix, expert_ids, expert_meta


def compute_top_n_overlap(cache: dict, top_n: int = 30) -> tuple[np.ndarray, list[str]]:
    """计算专家Top-N选股Jaccard重叠度矩阵

    方法: 对每个调仓日, 取每个专家的Top-N股票集合,
         计算两两专家的Jaccard相似度, 跨所有调仓日平均。

    Jaccard(A, B) = |A ∩ B| / |A ∪ B|
    """
    rebalance_dates = cache["rebalance_dates"]
    expert_ids = [e["expert_id"] for e in rebalance_dates[0]["expert_predictions"]]
    n_experts = len(expert_ids)

    print(f"\n计算Top-{top_n}选股Jaccard重叠度: {n_experts} 专家 × {len(rebalance_dates)} 调仓日")

    overlap_sum = np.zeros((n_experts, n_experts))
    overlap_count = 0

    for entry in rebalance_dates:
        expert_preds = entry["expert_predictions"]
        if len(expert_preds) != n_experts:
            continue

        # 计算每个专家的top-N
        top_sets = []
        for e in expert_preds:
            preds = e["predictions"]
            valid = [(c, v) for c, v in preds.items()
                     if v is not None and not (isinstance(v, float) and np.isnan(v))]
            valid.sort(key=lambda x: x[1], reverse=True)
            top_sets.append(set(c for c, _ in valid[:top_n]))

        # 计算两两Jaccard
        for i in range(n_experts):
            for j in range(i, n_experts):
                A, B = top_sets[i], top_sets[j]
                if not A and not B:
                    jac = 1.0
                elif not A or not B:
                    jac = 0.0
                else:
                    jac = len(A & B) / len(A | B)
                overlap_sum[i, j] += jac
                overlap_sum[j, i] += jac
        overlap_count += 1

    if overlap_count == 0:
        raise RuntimeError("无有效数据计算重叠度")

    overlap_matrix = overlap_sum / overlap_count
    return overlap_matrix, expert_ids


# ====================================================================
# 3. 分维度统计
# ====================================================================

def analyze_by_dimension(corr_matrix: np.ndarray, expert_meta: list[dict],
                          expert_ids: list[str]) -> dict:
    """按每个维度分组, 计算组内/组间平均相关性

    判断哪个维度对专家差异化的贡献最大/最小。
    """
    n = len(expert_ids)
    dims = ["model_type", "hyper_set", "feature_set", "train_window"]
    result = {}

    for dim in dims:
        groups = {}
        for i, meta in enumerate(expert_meta):
            key = meta[dim]
            groups.setdefault(key, []).append(i)

        # 组内平均相关性 (排除对角线1.0)
        within = []
        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            for i in idxs:
                for j in idxs:
                    if i != j:
                        within.append(corr_matrix[i, j])

        # 组间平均相关性
        between = []
        keys = list(groups.keys())
        for ki in range(len(keys)):
            for kj in range(ki + 1, len(keys)):
                for i in groups[keys[ki]]:
                    for j in groups[keys[kj]]:
                        between.append(corr_matrix[i, j])

        result[dim] = {
            "groups": {k: len(v) for k, v in groups.items()},
            "within_mean_corr": float(np.mean(within)) if within else 0,
            "between_mean_corr": float(np.mean(between)) if between else 0,
            "discrimination": (float(np.mean(between)) - float(np.mean(within))) if between and within else 0,
            # discrimination > 0 表示组间差异 > 组内差异, 该维度有效区分专家
        }

    return result


def identify_redundant_pairs(corr_matrix: np.ndarray, overlap_matrix: np.ndarray,
                               expert_ids: list[str], expert_meta: list[dict],
                               corr_threshold: float = 0.95,
                               overlap_threshold: float = 0.85) -> list[dict]:
    """识别冗余专家对"""
    n = len(expert_ids)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            corr = corr_matrix[i, j]
            ov = overlap_matrix[i, j]
            if corr >= corr_threshold or ov >= overlap_threshold:
                pairs.append({
                    "expert_a": expert_ids[i],
                    "expert_b": expert_ids[j],
                    "correlation": float(corr),
                    "overlap": float(ov),
                    "meta_a": expert_meta[i],
                    "meta_b": expert_meta[j],
                })
    # 按相关性降序
    pairs.sort(key=lambda x: x["correlation"], reverse=True)
    return pairs


def compute_expert_ic_stats(cache: dict) -> dict:
    """统计各专家IC分布 (跨所有调仓日)"""
    rebalance_dates = cache["rebalance_dates"]
    if not rebalance_dates:
        return {}

    expert_ids = [e["expert_id"] for e in rebalance_dates[0]["expert_predictions"]]
    ic_by_expert = {eid: [] for eid in expert_ids}

    for entry in rebalance_dates:
        for e in entry["expert_predictions"]:
            eid = e["expert_id"]
            ic = e.get("ic", 0.0)
            if eid in ic_by_expert:
                ic_by_expert[eid].append(ic)

    stats = {}
    for eid, ics in ic_by_expert.items():
        ics = np.array(ics) if ics else np.array([0.0])
        stats[eid] = {
            "mean_ic": float(np.mean(ics)),
            "std_ic": float(np.std(ics)),
            "positive_rate": float(np.mean(ics > 0)),
            "n": len(ics),
        }
    return stats


# ====================================================================
# 4. 可视化
# ====================================================================

def plot_matrix(matrix: np.ndarray, labels: list[str], title: str,
                save_path: Path, cmap: str = "RdYlGn_r"):
    """绘制矩阵热力图"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"  matplotlib未安装, 跳过绘图: {save_path}")
        return

    fig, ax = plt.subplots(figsize=(14, 12))
    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect="equal")

    # 标签
    short_labels = [l.replace("_conservative", "_cons").replace("_moderate", "_mod")
                     .replace("_momentum", "_mom").replace("_fundamental", "_fund")
                     .replace("_w252", "_1y").replace("_w504", "_2y")
                     for l in labels]
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(short_labels, rotation=90, fontsize=8)
    ax.set_yticklabels(short_labels, fontsize=8)
    ax.set_title(title, fontsize=14, pad=15)

    # 在格子中标数值
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = matrix[i, j]
            color = "white" if val > 0.7 or val < 0.3 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=color, fontsize=6)

    fig.colorbar(im, ax=ax, shrink=0.7)
    plt.tight_layout()
    plt.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  热力图已保存: {save_path}")


# ====================================================================
# 5. 报告生成
# ====================================================================

def generate_report(cache: dict, corr_matrix: np.ndarray, overlap_matrix: np.ndarray,
                     expert_ids: list[str], expert_meta: list[dict],
                     dim_analysis: dict, redundant_pairs: list[dict],
                     ic_stats: dict) -> str:
    """生成分析报告"""
    metrics = cache.get("metrics", {})
    n_dates = len(cache["rebalance_dates"])
    n_experts = len(expert_ids)

    lines = []
    lines.append("# expertForest_v1 专家行为相关性分析报告")
    lines.append("")
    cfg = cache["config"]
    lines.append(f"> 区间: {cfg['start']} → {cfg['end']} | 股票池: {cfg['pool']} | Top-{cfg['top_n']}")
    lines.append(f"> 调仓日数: {n_dates} | 专家数: {n_experts} | 集成: {cfg['ensemble']}")
    lines.append(f"> IS Sharpe: {metrics.get('sharpe', 0):.4f} | 超额: {metrics.get('excess_return', 0):+.2%}")
    lines.append("")

    # 冗余专家对
    lines.append("## 1. 冗余专家对 (核心发现)")
    lines.append("")
    lines.append(f"> 阈值: 相关性 ≥ 0.95 或 Top-30 Jaccard ≥ 0.85")
    lines.append(f"> 共发现 **{len(redundant_pairs)}** 对冗余专家")
    lines.append("")

    if redundant_pairs:
        lines.append("| # | 专家A | 专家B | 相关性 | Top30重叠 | 共同维度 |")
        lines.append("|---|-------|-------|--------|-----------|----------|")
        for i, p in enumerate(redundant_pairs[:30], 1):
            ma, mb = p["meta_a"], p["meta_b"]
            common = []
            for k in ["model_type", "hyper_set", "feature_set", "train_window"]:
                if ma[k] == mb[k]:
                    common.append(f"{k}={ma[k]}")
            common_str = ", ".join(common) if common else "(无)"
            lines.append(
                f"| {i} | {p['expert_a']} | {p['expert_b']} | "
                f"**{p['correlation']:.4f}** | **{p['overlap']:.4f}** | {common_str} |"
            )
        if len(redundant_pairs) > 30:
            lines.append(f"\n*... 共 {len(redundant_pairs)} 对, 仅显示前30 *")
    lines.append("")

    # 分维度区分度
    lines.append("## 2. 各维度对专家差异化的贡献")
    lines.append("")
    lines.append("> discrimination = 组间平均相关性 - 组内平均相关性")
    lines.append("> discrimination **越大** 表示该维度越能区分专家行为 (越有效)")
    lines.append("> discrimination **接近0或为负** 表示该维度无法区分 (冗余维度)")
    lines.append("")
    lines.append("| 维度 | 组内平均相关性 | 组间平均相关性 | 区分度 | 分组 | 评价 |")
    lines.append("|------|---------------|---------------|--------|------|------|")

    # 按区分度排序
    dim_sorted = sorted(dim_analysis.items(), key=lambda x: x[1]["discrimination"], reverse=True)
    for dim, info in dim_sorted:
        groups_str = ", ".join(f"{k}={v}" for k, v in info["groups"].items())
        disc = info["discrimination"]
        if disc > 0.05:
            verdict = "✓ 有效区分"
        elif disc > 0.01:
            verdict = "△ 弱区分"
        else:
            verdict = "✗ **无区分(冗余)**"
        lines.append(
            f"| {dim} | {info['within_mean_corr']:.4f} | {info['between_mean_corr']:.4f} | "
            f"{disc:+.4f} | {groups_str} | {verdict} |"
        )
    lines.append("")

    # 整体相关性分布
    lines.append("## 3. 专家预测相关性分布")
    lines.append("")
    upper_tri = corr_matrix[np.triu_indices(n_experts, k=1)]
    lines.append("| 统计项 | 值 |")
    lines.append("|--------|------|")
    lines.append(f"| 平均相关性 | {np.mean(upper_tri):.4f} |")
    lines.append(f"| 中位相关性 | {np.median(upper_tri):.4f} |")
    lines.append(f"| 最小相关性 | {np.min(upper_tri):.4f} |")
    lines.append(f"| 最大相关性 | {np.max(upper_tri):.4f} |")
    lines.append(f"| 相关性>0.95 的对数 | {int(np.sum(upper_tri > 0.95))} |")
    lines.append(f"| 相关性>0.90 的对数 | {int(np.sum(upper_tri > 0.90))} |")
    lines.append(f"| 相关性>0.80 的对数 | {int(np.sum(upper_tri > 0.80))} |")
    lines.append("")

    # 选股重叠度分布
    lines.append("## 4. Top-30 选股重叠度分布")
    lines.append("")
    upper_ov = overlap_matrix[np.triu_indices(n_experts, k=1)]
    lines.append("| 统计项 | 值 |")
    lines.append("|--------|------|")
    lines.append(f"| 平均重叠度 | {np.mean(upper_ov):.4f} |")
    lines.append(f"| 中位重叠度 | {np.median(upper_ov):.4f} |")
    lines.append(f"| 最小重叠度 | {np.min(upper_ov):.4f} |")
    lines.append(f"| 最大重叠度 | {np.max(upper_ov):.4f} |")
    lines.append(f"| 重叠度>0.85 的对数 | {int(np.sum(upper_ov > 0.85))} |")
    lines.append(f"| 重叠度>0.70 的对数 | {int(np.sum(upper_ov > 0.70))} |")
    lines.append("")

    # 专家IC对比
    lines.append("## 5. 各专家IC对比 (预测能力)")
    lines.append("")
    lines.append("| 专家 | 模型 | 超参 | 特征集 | 窗口 | 平均IC | IC标准差 | IC正率 |")
    lines.append("|------|------|------|--------|------|--------|----------|--------|")

    # 按平均IC降序
    ic_sorted = sorted(ic_stats.items(), key=lambda x: x[1]["mean_ic"], reverse=True)
    for eid, st in ic_sorted:
        meta = parse_expert_id(eid)
        lines.append(
            f"| {eid} | {meta['model_type']} | {meta['hyper_set']} | "
            f"{meta['feature_set']} | {meta['train_window']} | "
            f"{st['mean_ic']:+.4f} | {st['std_ic']:.4f} | {st['positive_rate']:.1%} |"
        )
    lines.append("")

    # 优化建议
    lines.append("## 6. 优化建议")
    lines.append("")

    # 基于分析自动生成建议
    suggestions = []

    # 找区分度最低的维度
    weakest_dim = dim_sorted[-1] if dim_sorted else None
    if weakest_dim and weakest_dim[1]["discrimination"] < 0.01:
        suggestions.append(
            f"- **{weakest_dim[0]}** 维度区分度极低 ({weakest_dim[1]['discrimination']:+.4f}), "
            f"组内/组间相关性几乎一致, 考虑移除该维度减少冗余专家"
        )

    # 找区分度最高的维度
    strongest_dim = dim_sorted[0] if dim_sorted else None
    if strongest_dim and strongest_dim[1]["discrimination"] > 0.05:
        suggestions.append(
            f"- **{strongest_dim[0]}** 维度区分度最高 ({strongest_dim[1]['discrimination']:+.4f}), "
            f"可考虑在该维度上增加更多差异化选项"
        )

    # 冗余专家数量
    if len(redundant_pairs) > 10:
        suggestions.append(
            f"- 共 {len(redundant_pairs)} 对冗余专家, 建议精简专家池或替换为差异化专家 "
            f"(如新增不同预测horizon/不同特征子集/不同基准的专家)"
        )
    elif len(redundant_pairs) > 0:
        suggestions.append(
            f"- 共 {len(redundant_pairs)} 对冗余专家, 数量可控, 可针对性优化"
        )
    else:
        suggestions.append(
            f"- 无高度冗余专家对 (相关性<0.95 且 重叠度<0.85), 专家差异化良好"
        )

    # 整体相关性水平
    avg_corr = np.mean(upper_tri)
    if avg_corr > 0.9:
        suggestions.append(
            f"- 整体平均相关性 {avg_corr:.4f} 偏高, 专家行为趋同, 建议大幅增加差异化"
        )
    elif avg_corr > 0.7:
        suggestions.append(
            f"- 整体平均相关性 {avg_corr:.4f} 中等, 有一定差异化空间"
        )
    else:
        suggestions.append(
            f"- 整体平均相关性 {avg_corr:.4f} 较低, 专家差异化良好"
        )

    # 新增数据建议
    suggestions.append("")
    suggestions.append("### 可新增的差异化专家方向 (基于未使用数据)")
    suggestions.append("- **融资融券专家**: 利用 stock_margin_trading (融资融券余额/买入额, 与现有因子无重叠)")
    suggestions.append("- **龙虎榜情绪专家**: 利用 stock_billboard (上榜次数/机构净买入, 事件型情绪因子)")
    suggestions.append("- **解禁压力专家**: 利用 stock_locked_shares (解禁量/流通市值比, 事件型)")
    suggestions.append("- **大单资金流专家**: 利用 stock_money_flow (大单/超大单净流入, 细粒度补充)")
    suggestions.append("- **行业轮动专家**: 利用 stock_industry (申万行业归属, 行业动量/中性化)")
    suggestions.append("- **不同预测horizon**: 10日/20日前向收益 (当前统一5日)")
    suggestions.append("- **不同基准**: 相对000905/000852基准的超额收益 (当前统一000300)")

    for s in suggestions:
        lines.append(s)
    lines.append("")

    lines.append("## 附: 文件说明")
    lines.append("- `expert_corr_matrix.png`: 专家预测相关性热力图 (32×32)")
    lines.append("- `expert_overlap_matrix.png`: Top-30选股重叠度热力图 (32×32)")
    lines.append("- `expert_predictions_cache.json`: 专家预测缓存 (避免重复跑回测)")
    lines.append("")

    return "\n".join(lines)


# ====================================================================
# 主流程
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="expertForest_v1 专家相关性分析")
    parser.add_argument("--start", default="2024-01-01", help="IS开始日期")
    parser.add_argument("--end", default="2025-12-31", help="IS结束日期")
    parser.add_argument("--data-start", default="2022-01-01", help="训练数据起始")
    parser.add_argument("--short", action="store_true", help="短区间快速分析(2025下半年)")
    parser.add_argument("--use-cache", action="store_true", help="复用缓存(不跑回测)")
    parser.add_argument("--corr-threshold", type=float, default=0.95, help="冗余相关性阈值")
    parser.add_argument("--overlap-threshold", type=float, default=0.85, help="冗余重叠度阈值")
    args = parser.parse_args()

    if args.short:
        args.start = "2025-07-01"
        args.end = "2025-12-31"
        args.data_start = "2024-01-01"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 获取数据 (运行回测 or 复用缓存)
    if args.use_cache and CACHE_FILE.exists():
        print(f"复用缓存: {CACHE_FILE}")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(f"  调仓日数: {len(cache['rebalance_dates'])}")
        print(f"  IS Sharpe: {cache.get('metrics', {}).get('sharpe', 0):.4f}")
    else:
        cache = run_backtest_and_cache(args.start, args.end, args.data_start)

    # 2. 计算相关性矩阵
    print("\n" + "=" * 60)
    print("  分析专家行为")
    print("=" * 60)
    corr_matrix, expert_ids, expert_meta = compute_expert_correlation(cache)

    # 3. 计算选股重叠度
    overlap_matrix, _ = compute_top_n_overlap(cache, top_n=TOP_N)

    # 4. 分维度统计
    dim_analysis = analyze_by_dimension(corr_matrix, expert_meta, expert_ids)

    # 5. 识别冗余对
    redundant_pairs = identify_redundant_pairs(
        corr_matrix, overlap_matrix, expert_ids, expert_meta,
        args.corr_threshold, args.overlap_threshold
    )

    # 6. IC统计
    ic_stats = compute_expert_ic_stats(cache)

    # 7. 绘图
    print("\n生成热力图...")
    plot_matrix(corr_matrix, expert_ids,
                f"专家预测相关性矩阵 (Spearman, {args.start}~{args.end})",
                OUTPUT_DIR / "expert_corr_matrix.png", cmap="RdYlGn_r")
    plot_matrix(overlap_matrix, expert_ids,
                f"Top-{TOP_N} 选股Jaccard重叠度 ({args.start}~{args.end})",
                OUTPUT_DIR / "expert_overlap_matrix.png", cmap="YlOrRd")

    # 8. 生成报告
    report = generate_report(
        cache, corr_matrix, overlap_matrix, expert_ids, expert_meta,
        dim_analysis, redundant_pairs, ic_stats
    )
    report_path = OUTPUT_DIR / "correlation_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {report_path}")

    # 9. 打印关键结论
    print("\n" + "=" * 60)
    print("  关键结论")
    print("=" * 60)
    upper_corr = corr_matrix[np.triu_indices(len(expert_ids), k=1)]
    upper_ov = overlap_matrix[np.triu_indices(len(expert_ids), k=1)]
    print(f"平均预测相关性: {np.mean(upper_corr):.4f}")
    print(f"平均选股重叠度: {np.mean(upper_ov):.4f}")
    print(f"冗余专家对数: {len(redundant_pairs)} (相关性≥{args.corr_threshold} 或 重叠度≥{args.overlap_threshold})")

    print(f"\n各维度区分度 (越大越有效):")
    for dim, info in sorted(dim_analysis.items(), key=lambda x: x[1]["discrimination"], reverse=True):
        print(f"  {dim:15s}: 组内={info['within_mean_corr']:.4f}  组间={info['between_mean_corr']:.4f}  区分度={info['discrimination']:+.4f}")

    if redundant_pairs:
        print(f"\nTop 5 最冗余专家对:")
        for p in redundant_pairs[:5]:
            print(f"  {p['expert_a']} <-> {p['expert_b']}: corr={p['correlation']:.4f} overlap={p['overlap']:.4f}")


if __name__ == "__main__":
    main()
