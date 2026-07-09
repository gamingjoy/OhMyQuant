"""全策略对比脚本"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

strategies = {
    "ycj_v1": "output/ycj_v1/results.json",
    "ycj_v2": "output/ycj_v2/results.json",
    "dh_v1": "output/dh_v1/results.json",
    "etf_v1": "output/etf_v1/results.json",
    "etf_v2": "output/etf_v2/results.json",
    "dl_v1": "output/dl_v1/results.json",
    "rl_v1": "output/rl_v1/results.json",
}

results = {}
for name, path in strategies.items():
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        results[name] = d["metrics"]

print("=" * 110)
header = f"{'策略':<10} {'年化收益':>10} {'年化波动':>10} {'Sharpe':>10} {'Sortino':>10} {'最大回撤':>10} {'Calmar':>10} {'胜率':>10}"
print(header)
print("=" * 110)
for name, m in sorted(results.items(), key=lambda x: -x[1]["sharpe_ratio"]):
    row = (
        f"{name:<10} "
        f"{m['annualized_return']:>10.2%} "
        f"{m['annualized_volatility']:>10.2%} "
        f"{m['sharpe_ratio']:>10.4f} "
        f"{m['sortino_ratio']:>10.4f} "
        f"{m['max_drawdown']:>10.2%} "
        f"{m['calmar_ratio']:>10.4f} "
        f"{m['win_rate']:>10.2%}"
    )
    print(row)
print("=" * 110)
print(f"共 {len(results)} 个策略")

# 相关性矩阵
if len(results) >= 2:
    import numpy as np

    returns = {}
    for name, path in strategies.items():
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "daily_returns" in d and d["daily_returns"]:
                returns[name] = np.array(d["daily_returns"])

    if len(returns) >= 2:
        min_len = min(len(r) for r in returns.values())
        aligned = {name: r[:min_len] for name, r in returns.items()}
        names = list(aligned.keys())
        matrix = np.corrcoef([aligned[n] for n in names])

        print("\n相关性矩阵:")
        print(f"{'':<10}", end="")
        for n in names:
            print(f"{n:>10}", end="")
        print()
        for i, n in enumerate(names):
            print(f"{n:<10}", end="")
            for j in range(len(names)):
                print(f"{matrix[i][j]:>10.4f}", end="")
            print()
