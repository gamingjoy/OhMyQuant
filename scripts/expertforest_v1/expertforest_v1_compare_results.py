"""expertForest_v1 配置对比汇总脚本

读取所有IS回测结果JSON, 汇总对比不同池子×N值的表现。

用法:
    python scripts/expertforest_v1_compare_results.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main():
    results_dir = Path("output/is_compare/expertforest_v1")
    if not results_dir.exists():
        print(f"结果目录不存在: {results_dir}")
        sys.exit(1)

    json_files = sorted(results_dir.glob("expertforest_v1_*.json"))
    if not json_files:
        print(f"未找到结果文件: {results_dir}/expertforest_v1_*.json")
        sys.exit(1)

    print(f"找到 {len(json_files)} 个结果文件\n")

    # 收集所有结果
    all_results = []
    for f in json_files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        cfg = data.get("config", {})
        metrics = data.get("metrics", {})
        all_results.append({
            "pool": cfg.get("pool", "?"),
            "top_n": cfg.get("top_n", "?"),
            "start": cfg.get("start", "?"),
            "end": cfg.get("end", "?"),
            "cum_return": metrics.get("cum_return", float("nan")),
            "excess_return": metrics.get("excess_return", float("nan")),
            "annual_return": metrics.get("annual_return", float("nan")),
            "sharpe": metrics.get("sharpe", float("nan")),
            "max_drawdown": metrics.get("max_drawdown", float("nan")),
            "ir": metrics.get("ir", metrics.get("excess_sharpe", float("nan"))),
            "calmar": metrics.get("calmar", float("nan")),
            "win_rate": metrics.get("monthly_win_rate", metrics.get("win_rate", float("nan"))),
            "elapsed_sec": data.get("elapsed_sec", 0),
        })

    # 按池子分组
    pools = {}
    for r in all_results:
        p = r["pool"]
        if p not in pools:
            pools[p] = []
        pools[p].append(r)

    # 打印汇总表
    print("=" * 120)
    print(f"{'池子':<20} {'N':>3} {'累计收益':>10} {'超额收益':>10} {'年化收益':>10} {'Sharpe':>8} {'最大回撤':>10} {'IR':>8} {'Calmar':>8} {'月胜率':>8}")
    print("=" * 120)

    for pool_name in sorted(pools.keys()):
        for r in sorted(pools[pool_name], key=lambda x: x["top_n"]):
            def fmt(v, suffix="%"):
                if isinstance(v, (int, float)):
                    return f"{v*100:.2f}{suffix}" if abs(v) < 10 else f"{v:.4f}"
                return str(v)

            def fmt_pct(v):
                if isinstance(v, (int, float)):
                    return f"{v*100:.2f}%"
                return "N/A"

            def fmt_num(v):
                if isinstance(v, (int, float)):
                    return f"{v:.4f}"
                return "N/A"

            print(
                f"{pool_name:<20} {r['top_n']:>3} "
                f"{fmt_pct(r['cum_return']):>10} "
                f"{fmt_pct(r['excess_return']):>10} "
                f"{fmt_pct(r['annual_return']):>10} "
                f"{fmt_num(r['sharpe']):>8} "
                f"{fmt_pct(r['max_drawdown']):>10} "
                f"{fmt_num(r['ir']):>8} "
                f"{fmt_num(r['calmar']):>8} "
                f"{fmt_pct(r['win_rate']):>8}"
            )
        print("-" * 120)

    # 找最优配置
    print("\n最优配置 (按Sharpe排序):")
    sorted_results = sorted(all_results, key=lambda x: x["sharpe"] if isinstance(x["sharpe"], (int, float)) else -999, reverse=True)
    for i, r in enumerate(sorted_results[:5]):
        print(
            f"  #{i+1}: {r['pool']} N={r['top_n']} | "
            f"Sharpe={r['sharpe']:.4f} | "
            f"超额={r['excess_return']*100:.2f}% | "
            f"回撤={r['max_drawdown']*100:.2f}% | "
            f"Calmar={r['calmar']:.4f}"
        )

    # 保存汇总JSON
    summary_file = results_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n汇总已保存: {summary_file}")


if __name__ == "__main__":
    main()
