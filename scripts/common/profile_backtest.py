"""回测引擎性能分析脚本

使用 cProfile 分析回测热点，识别性能瓶颈。

用法:
    python scripts/common/profile_backtest.py [--strategy industry_rotation] [--version v66] [--top 20]

前提:
    - data/ 目录存在且有完整数据
    - pip install -e ".[dev]"

输出:
    - 控制台打印 Top-N 热点函数
    - profile.out 二进制文件（可用 pstats 分析）
"""
from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
from io import StringIO


def profile_backtest(strategy_type: str = "industry_rotation",
                     version: str = "v66",
                     top_n: int = 20) -> None:
    """运行 cProfile 分析回测性能

    Args:
        strategy_type: 策略类型
        version: 策略版本
        top_n: 显示热点函数数量
    """
    from ohmyquant.strategy.runner import StrategyRunner

    print(f"性能分析: {strategy_type} {version}")
    print(f"输出 Top-{top_n} 热点函数\n")

    profiler = cProfile.Profile()
    profiler.enable()

    try:
        StrategyRunner.run_strategy(strategy_type, version)
    except Exception as e:
        print(f"回测出错（不影响性能分析）: {e}")
    finally:
        profiler.disable()

    # 保存完整 profile
    profiler.dump_stats("profile.out")
    print("完整 profile 已保存到 profile.out\n")

    # 打印 Top-N 热点（按 cumulative time 排序）
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(top_n)
    print(stream.getvalue())

    # 按 tottime（自身耗时）排序
    stream2 = StringIO()
    stats2 = pstats.Stats(profiler, stream=stream2)
    stats2.sort_stats("tottime")
    stats2.print_stats(top_n)
    print("=== 按自身耗时排序 ===")
    print(stream2.getvalue())

    # 分析建议
    print("\n=== 优化建议 ===")
    print("1. 查看 cumtime 最高的函数 → 优化整体流程")
    print("2. 查看 tottime 最高的函数 → 优化计算密集型代码")
    print("3. 关注 polars/duckdb 相关函数 → 数据加载是否过慢")
    print("4. 关注因子计算函数 → 是否有重复计算")
    print("5. 用 'python -m pstats profile.out' 交互式分析")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回测性能分析")
    parser.add_argument("--strategy", default="industry_rotation", help="策略类型")
    parser.add_argument("--version", default="v66", help="策略版本")
    parser.add_argument("--top", type=int, default=20, help="显示热点函数数量")
    args = parser.parse_args()

    profile_backtest(args.strategy, args.version, args.top)
