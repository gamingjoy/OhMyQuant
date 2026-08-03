"""expertForest_v1 全自动流水线: 监控当前批次完成后自动启动下一批

监控逻辑:
  1. 检测当前正在运行的expertforest_v1进程数
  2. 当进程数降为0时, 启动下一批
  3. 3批依次执行: HS300 → ZZ500 → ZZ800

用法:
    python -u scripts/expertforest_v1_pipeline.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# 3批配置: (池子名称, 池子代码, N值列表)
BATCHES = [
    ("hs300", "000300.XSHG",   [10, 15, 20, 30]),
    ("zz500", "000905.XSHG",   [10, 15, 20, 30]),
    ("zz800", "000300.XSHG+000905.XSHG", [10, 15, 20, 30]),
]

N_JOBS = 8
START = "2023-01-01"
END = "2025-12-31"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def wait_for_batch_completion(pool_name: str):
    """等待指定池子的批次完成(所有4个进程结束)"""
    print(f"  等待 {pool_name} 批次完成...", flush=True)
    while True:
        n = count_expertforest_processes()
        if n == 0:
            print(f"  {pool_name} 批次完成!", flush=True)
            return
        time.sleep(60)  # 每分钟检查一次


def launch_batch(pool_name: str, pool_code: str, n_values: list[int]):
    """启动一批4个并行IS回测"""
    print(f"\n{'='*70}", flush=True)
    print(f"  启动批次: {pool_name} ({pool_code})", flush=True)
    print(f"  N值: {n_values}", flush=True)
    print(f"  n_jobs: {N_JOBS}", flush=True)
    print(f"  区间: {START} → {END}", flush=True)
    print(f"{'='*70}", flush=True)

    for n in n_values:
        log_file = PROJECT_ROOT / "output" / f"expertforest_v1_is_{pool_name}_n{n}.log"
        # 直接启动python进程, 输出重定向到日志文件
        log_fp = open(log_file, "w", encoding="utf-8")
        subprocess.Popen(
            [
                sys.executable, "-u", "scripts/expertforest_v1_is_explore.py",
                "--pool", pool_code,
                "--top_n", str(n),
                "--start", START,
                "--end", END,
                "--n_jobs", str(N_JOBS),
            ],
            cwd=str(PROJECT_ROOT),
            stdout=log_fp,
            stderr=subprocess.STDOUT,
        )
        print(f"  已启动: {pool_name} N={n} → {log_file.name}", flush=True)
        time.sleep(3)  # 错开启动避免I/O峰值

    print(f"\n  4个进程已启动", flush=True)


def main():
    print(f"expertForest_v1 全自动流水线", flush=True)
    print(f"  3批 × 4配置 = 12个IS回测", flush=True)
    print(f"  每批n_jobs={N_JOBS}×4进程=32核", flush=True)
    print(f"  开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    for i, (pool_name, pool_code, n_values) in enumerate(BATCHES):
        if i == 0:
            # 第一批: 检查是否已经在运行
            n_running = count_expertforest_processes()
            if n_running > 0:
                print(f"\n检测到 {n_running} 个expertforest_v1进程正在运行, 等待完成...", flush=True)
                wait_for_batch_completion(pool_name)
            else:
                launch_batch(pool_name, pool_code, n_values)
                wait_for_batch_completion(pool_name)
        else:
            # 后续批次: 直接启动
            launch_batch(pool_name, pool_code, n_values)
            wait_for_batch_completion(pool_name)

        print(f"\n批次 {pool_name} 完成!", flush=True)

    # 全部完成, 运行对比脚本
    print(f"\n{'='*70}", flush=True)
    print(f"  全部12个配置完成! 运行结果对比...", flush=True)
    print(f"{'='*70}", flush=True)

    result = subprocess.run(
        ["python", "scripts/expertforest_v1_compare_results.py"],
        cwd=str(PROJECT_ROOT),
    )

    print(f"\n流水线完成! 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)


if __name__ == "__main__":
    main()
