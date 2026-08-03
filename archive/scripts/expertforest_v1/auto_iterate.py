"""expertForest_v1 全自动迭代脚本 — 无需人工介入

执行流程:
  0. 等待当前所有expertforest_v1进程完成 (ZZ800×4)
  1. 读取所有结果, 找最优配置(pool+N)
  2. Phase 2: 3种集成方法 × 最优pool+N → 等待完成
  3. 读取结果, 找最优集成方法 → 检查收敛
  4. Phase 3: 3种特征集 × 最优pool+N+集成 → 等待完成
  5. 读取结果, 找最优特征集 → 检查收敛
  6. Phase 4: 超参变体 × 最优配置 → 等待完成
  7. 检查收敛, 若Sharpe提升<0.01则停止, 否则继续

收敛标准: 相邻Phase间Sharpe提升 < 0.01

用法:
    python -u scripts/expertforest_v1_auto_iterate.py 2>&1 | Tee-Object -FilePath output/expertforest_v1_auto_iterate.log
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "output" / "is_compare" / "expertforest_v1"
LOG_FILE = PROJECT_ROOT / "output" / "expertforest_v1_auto_iterate.log"

# 串行运行, 每进程用全核32 (避免并行时n_jobs稀释导致RF/ET建树过慢)
N_JOBS_PER_PROC = 32
START = "2023-01-01"
END = "2025-12-31"


def log(msg: str):
    """带时间戳的日志"""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def count_expertforest_processes() -> int:
    """统计正在运行的expertforest_v1_is_explore进程数"""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*expertforest_v1_is_explore*' }).Count"],
            capture_output=True, text=True, timeout=10
        )
        return int(result.stdout.strip()) if result.stdout.strip() else 0
    except Exception:
        return 0


def wait_for_completion(phase_name: str = ""):
    """等待所有expertforest_v1进程完成"""
    if phase_name:
        log(f"等待 {phase_name} 完成...")
    while True:
        n = count_expertforest_processes()
        if n == 0:
            log(f"所有进程完成!")
            return
        log(f"  仍有 {n} 个进程运行中, 等待60s...")
        time.sleep(60)


def read_all_results() -> list[dict]:
    """读取所有结果JSON"""
    results = []
    for f in sorted(RESULTS_DIR.glob("expertforest_v1_*.json")):
        if f.name == "summary.json":
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            cfg = data.get("config", {})
            metrics = data.get("metrics", {})
            # 只保留3年IS结果(非smoke)
            if cfg.get("smoke"):
                continue
            if cfg.get("start") != START:
                continue
            results.append({
                "file": f.name,
                "pool": cfg.get("pool", ""),
                "top_n": cfg.get("top_n", 10),
                "ensemble": cfg.get("ensemble", "equal_weight"),
                "feature_sets": cfg.get("feature_sets", None),
                "sharpe": metrics.get("sharpe", 0),
                "excess_return": metrics.get("excess_return", 0),
                "max_drawdown": metrics.get("max_drawdown", 0),
                "calmar": metrics.get("calmar", 0),
                "win_rate": metrics.get("monthly_win_rate", metrics.get("win_rate", 0)),
            })
        except Exception as e:
            log(f"  读取 {f.name} 失败: {e}")
    return results


def find_best(results: list[dict]) -> dict | None:
    """找Sharpe最高的配置"""
    if not results:
        return None
    return max(results, key=lambda x: x["sharpe"] if isinstance(x["sharpe"], (int, float)) else 0)


def launch_configs(configs: list[dict], n_jobs: int, phase_tag: str):
    """串行启动IS回测配置(每个用全核, 运行完一个再启动下一个)

    串行+全核比并行+n_jobs稀释快得多:
    - 串行n_jobs=32: 25h/配置 × N配置
    - 并行n_jobs=10: 83h/配置 (3配置同时, 但每配置慢3.3x)
    """
    log(f"启动 {phase_tag}: {len(configs)}个配置, 串行, n_jobs={n_jobs}")
    for i, cfg in enumerate(configs):
        pool = cfg["pool"]
        top_n = cfg["top_n"]
        ensemble = cfg.get("ensemble", "equal_weight")
        feature_sets = cfg.get("feature_sets", None)

        # 构建日志文件名
        pool_short = pool.replace(".XSHG", "").replace("+", "plus")
        parts = [f"expertforest_v1_is_{pool_short}_n{top_n}_{ensemble}"]
        if feature_sets:
            parts.append(feature_sets.replace(",", "+"))
        tag = "_".join(parts)
        log_file = PROJECT_ROOT / "output" / f"{tag}.log"

        # 构建命令
        cmd = [
            sys.executable, "-u", "scripts/expertforest_v1_is_explore.py",
            "--pool", pool,
            "--top_n", str(top_n),
            "--start", START,
            "--end", END,
            "--n_jobs", str(n_jobs),
            "--ensemble", ensemble,
        ]
        if feature_sets:
            cmd += ["--feature_sets", feature_sets]

        log(f"  [{i+1}/{len(configs)}] {pool} N={top_n} {ensemble} fs={feature_sets} → {log_file.name}")
        t0 = time.time()
        with open(log_file, "w", encoding="utf-8") as log_fp:
            subprocess.run(cmd, cwd=str(PROJECT_ROOT), stdout=log_fp, stderr=subprocess.STDOUT)
        elapsed = time.time() - t0
        log(f"  [{i+1}/{len(configs)}] 完成 ({elapsed/60:.1f}min)")

    log(f"{phase_tag} 完成 {len(configs)} 个进程")


def check_convergence(old_sharpe: float, new_sharpe: float, phase_name: str) -> bool:
    """检查是否收敛 (Sharpe提升 < 0.01 表示无显著改善, 停止迭代)

    Returns:
        True: 已收敛(提升<0.01), 停止迭代
        False: 未收敛(提升>=0.01), 继续迭代
    """
    improvement = new_sharpe - old_sharpe
    log(f"收敛检查 [{phase_name}]: Sharpe {old_sharpe:.4f} → {new_sharpe:.4f} (提升 {improvement:+.4f})")
    if improvement < 0.01:
        log(f"  ✓ 已收敛(提升<0.01), 停止迭代")
        return True
    else:
        log(f"  ✗ 未收敛(提升>=0.01), 继续迭代")
        return False


def main():
    log("=" * 70)
    log("expertForest_v1 全自动迭代脚本启动")
    log(f"收敛标准: 相邻Phase间Sharpe提升 < 0.01")
    log(f"每Phase n_jobs={N_JOBS_PER_PROC}")
    log("=" * 70)

    # ========================================
    # Step 0: 等待当前进程完成 (ZZ800×4)
    # ========================================
    n = count_expertforest_processes()
    if n > 0:
        log(f"Step 0: 等待 {n} 个当前进程完成 (ZZ800等)")
        wait_for_completion("当前批次")

    # 读取所有结果
    results = read_all_results()
    best = find_best(results)
    if not best:
        log("错误: 未找到任何IS结果!")
        return

    log(f"\n当前最优配置:")
    log(f"  池子: {best['pool']}")
    log(f"  N: {best['top_n']}")
    log(f"  集成: {best['ensemble']}")
    log(f"  特征集: {best['feature_sets']}")
    log(f"  Sharpe: {best['sharpe']:.4f}")
    log(f"  超额收益: {best['excess_return']*100:.2f}%")
    log(f"  最大回撤: {best['max_drawdown']*100:.2f}%")
    log(f"  Calmar: {best['calmar']:.4f}")

    best_pool = best["pool"]
    best_n = best["top_n"]
    best_ensemble = best["ensemble"]
    best_fs = best["feature_sets"]
    prev_sharpe = best["sharpe"]

    # ========================================
    # Phase 2: 集成方法对比 (若尚未测试)
    # ========================================
    log(f"\n{'='*70}")
    log("Phase 2: 集成方法对比")
    log(f"{'='*70}")

    ensemble_methods = ["ic_weighted", "rank_average", "ic_rank_weighted"]
    # 过滤掉已测试的方法
    tested_ensembles = {r["ensemble"] for r in results
                        if r["pool"] == best_pool and r["top_n"] == best_n}
    new_methods = [m for m in ensemble_methods if m not in tested_ensembles]

    if new_methods:
        configs = [
            {"pool": best_pool, "top_n": best_n, "ensemble": m}
            for m in new_methods
        ]
        launch_configs(configs, N_JOBS_PER_PROC, "Phase 2")
        # launch_configs已串行阻塞, 无需wait_for_completion

        # 读取结果
        results = read_all_results()
        best = find_best(results)
        if best:
            log(f"\nPhase 2 最优:")
            log(f"  {best['pool']} N={best['top_n']} {best['ensemble']}")
            log(f"  Sharpe: {best['sharpe']:.4f} (此前: {prev_sharpe:.4f})")

            if check_convergence(prev_sharpe, best["sharpe"], "Phase 2"):
                log("Phase 2 已收敛, 停止迭代")
                _print_final(best, results)
                return

            prev_sharpe = best["sharpe"]
            best_ensemble = best["ensemble"]
            best_fs = best["feature_sets"]
    else:
        log("所有集成方法已测试, 跳过Phase 2")

    # ========================================
    # Phase 3: 特征集探索
    # ========================================
    log(f"\n{'='*70}")
    log("Phase 3: 特征集探索")
    log(f"{'='*70}")

    feature_sets_list = ["momentum", "fundamental", "combined"]
    # 过滤掉已测试的
    tested_fs = {r["feature_sets"] for r in results
                 if r["pool"] == best_pool and r["top_n"] == best_n
                 and r["ensemble"] == best_ensemble}
    new_fs = [fs for fs in feature_sets_list if fs not in tested_fs]

    if new_fs:
        configs = [
            {"pool": best_pool, "top_n": best_n, "ensemble": best_ensemble, "feature_sets": fs}
            for fs in new_fs
        ]
        launch_configs(configs, N_JOBS_PER_PROC, "Phase 3")
        # launch_configs已串行阻塞

        results = read_all_results()
        best = find_best(results)
        if best:
            log(f"\nPhase 3 最优:")
            log(f"  {best['pool']} N={best['top_n']} {best['ensemble']} fs={best['feature_sets']}")
            log(f"  Sharpe: {best['sharpe']:.4f} (此前: {prev_sharpe:.4f})")

            if check_convergence(prev_sharpe, best["sharpe"], "Phase 3"):
                log("Phase 3 已收敛, 停止迭代")
                _print_final(best, results)
                return

            prev_sharpe = best["sharpe"]
            best_fs = best["feature_sets"]
    else:
        log("所有特征集已测试, 跳过Phase 3")

    # ========================================
    # Phase 4: 超参变体 (用--fast模式测试不同model_types/windows组合)
    # ========================================
    log(f"\n{'='*70}")
    log("Phase 4: 超参变体探索 (特征集组合)")
    log(f"{'='*70}")

    # Phase 4: 测试不同特征集组合
    fs_combos = [
        "momentum,fundamental",   # 默认(已测试,作为baseline)
        "momentum,combined",
        "fundamental,combined",
        "momentum,fundamental,combined",
    ]
    tested_combos = {r["feature_sets"] for r in results
                     if r["pool"] == best_pool and r["top_n"] == best_n
                     and r["ensemble"] == best_ensemble}
    new_combos = [fc for fc in fs_combos if fc not in tested_combos]

    if new_combos:
        configs = [
            {"pool": best_pool, "top_n": best_n, "ensemble": best_ensemble, "feature_sets": fc}
            for fc in new_combos
        ]
        launch_configs(configs, N_JOBS_PER_PROC, "Phase 4")
        # launch_configs已串行阻塞

        results = read_all_results()
        best = find_best(results)
        if best:
            log(f"\nPhase 4 最优:")
            log(f"  {best['pool']} N={best['top_n']} {best['ensemble']} fs={best['feature_sets']}")
            log(f"  Sharpe: {best['sharpe']:.4f} (此前: {prev_sharpe:.4f})")

            if check_convergence(prev_sharpe, best["sharpe"], "Phase 4"):
                log("Phase 4 已收敛, 停止迭代")
                _print_final(best, results)
                return

            prev_sharpe = best["sharpe"]
            best_fs = best["feature_sets"]
    else:
        log("所有特征集组合已测试, 跳过Phase 4")

    # ========================================
    # 最终汇总
    # ========================================
    log(f"\n{'='*70}")
    log("所有Phase完成!")
    log(f"{'='*70}")
    _print_final(best, results)

    # 运行对比脚本
    log("\n运行结果对比脚本...")
    subprocess.run(
        [sys.executable, "scripts/expertforest_v1_compare_results.py"],
        cwd=str(PROJECT_ROOT),
    )
    log("全自动迭代完成!")


def _print_final(best: dict, all_results: list[dict]):
    """打印最终结果"""
    log(f"\n最终最优配置:")
    log(f"  池子: {best['pool']}")
    log(f"  N: {best['top_n']}")
    log(f"  集成: {best['ensemble']}")
    log(f"  特征集: {best['feature_sets']}")
    log(f"  Sharpe: {best['sharpe']:.4f}")
    log(f"  超额收益: {best['excess_return']*100:.2f}%")
    log(f"  最大回撤: {best['max_drawdown']*100:.2f}%")
    log(f"  Calmar: {best['calmar']:.4f}")
    log(f"  月胜率: {best['win_rate']*100:.1f}%")

    log(f"\n所有配置排名 (Top 10):")
    sorted_results = sorted(all_results, key=lambda x: x["sharpe"], reverse=True)
    for i, r in enumerate(sorted_results[:10]):
        log(f"  #{i+1}: {r['pool']} N={r['top_n']} {r['ensemble']} fs={r['feature_sets']} | "
            f"Sharpe={r['sharpe']:.4f} 超额={r['excess_return']*100:.1f}% 回撤={r['max_drawdown']*100:.1f}%")


if __name__ == "__main__":
    main()
