"""增量数据更新脚本

T日早晨执行，自动下载T-1数据，覆盖当年全量 + 前一年（跨年应对）。
无需指定YYYYMMDD参数，自动从本地最新日期推断。

用法:
    python scripts/update_data.py                # 完整更新
    python scripts/update_data.py --dry-run      # 预览不下载
    python scripts/update_data.py --skip-backup  # 跳过备份
    python scripts/update_data.py --force-rebuild  # 强制全量重建宽表

凭据从环境变量读取:
    $env:JQ_USERNAME="your_username"
    $env:JQ_PASSWORD="your_password"
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 确保能导入 ohmyquant 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(
        description="增量数据更新（T-1数据 + 当年全量 + 前一年）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/update_data.py
  python scripts/update_data.py --dry-run
  python scripts/update_data.py --force-rebuild
  python scripts/update_data.py --data-types stock_daily_price,index_daily_price
        """,
    )
    parser.add_argument(
        "--data-root",
        default="D:/Work/Project/download_a_share/data",
        help="数据根目录（默认: D:/Work/Project/download_a_share/data）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览将要下载的日期范围，不实际下载",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过下载步骤",
    )
    parser.add_argument(
        "--skip-wide-table",
        action="store_true",
        help="跳过宽表重建",
    )
    parser.add_argument(
        "--skip-factor",
        action="store_true",
        help="跳过因子更新",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="执行备份（默认跳过）",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="强制全量重建所有年份宽表分区",
    )
    parser.add_argument(
        "--data-types",
        help="指定下载的数据类型（逗号分隔），默认全部",
    )

    args = parser.parse_args()

    # 检查凭据
    username = os.getenv("JQ_USERNAME")
    password = os.getenv("JQ_PASSWORD")
    if not args.dry_run and not args.skip_download:
        if not username or not password:
            print("错误: 聚宽凭证未配置")
            print("请设置环境变量:")
            print('  $env:JQ_USERNAME="your_username"')
            print('  $env:JQ_PASSWORD="your_password"')
            sys.exit(1)
        print(f"凭据: JQ_USERNAME={username}")

    # 解析数据类型
    data_types = None
    if args.data_types:
        data_types = [t.strip() for t in args.data_types.split(",")]

    from ohmyquant.data.updater import DataUpdater

    updater = DataUpdater(
        data_root=args.data_root,
        jq_config={"username": username, "password": password} if username else {},
    )

    # 确定日期范围
    try:
        start_date, end_date = updater._get_target_date_range()
    except Exception as e:
        print(f"无法确定日期范围: {e}")
        print("首次运行，将从当年年初开始下载")
        year = datetime.now().year
        start_date = f"{year - 1}-01-01"
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"数据更新 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"数据目录: {args.data_root}")
    print(f"更新日期范围: {start_date} ~ {end_date}")
    if data_types:
        print(f"数据类型: {data_types}")
    else:
        print("数据类型: 全部")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY-RUN] 预览模式，不执行实际下载")
        print(f"  将下载 {start_date} ~ {end_date} 的数据")
        print(f"  数据目录: {args.data_root}")
        if data_types:
            print(f"  数据类型: {data_types}")
        else:
            print("  数据类型: 全部（stock_daily_price, stock_valuation, ... 等 19 种）")
        print("  宽表重建: 当年分区（周末全量重建）")
        print("\n实际执行请去掉 --dry-run 参数")
        return

    # 执行更新
    try:
        updater.run_daily_update(
            skip_download=args.skip_download,
            skip_wide_table=args.skip_wide_table,
            skip_factor=args.skip_factor,
            skip_backup=not args.backup,
            data_types=data_types,
            force_rebuild=args.force_rebuild,
        )
        print("\n数据更新完成")
    except Exception as e:
        print(f"\n数据更新失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
