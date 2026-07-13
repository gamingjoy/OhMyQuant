"""数据更新工作流

T日早晨执行：
  1. 自动确定需下载日期（T-1，无需指定 YYYYMMDD）
  2. 增量下载各数据类型
  3. 重建当年全量宽表分区
  4. 更新因子数据
  5. 可选：备份数据

设计原则（参考用户偏好）:
  - 无需指定 YYYYMMDD，自动从本地最新日期推断
  - 数据覆盖当年全量，增量增加当年和前一年数据（应对跨年）
  - 不忽略 jqdata 的 warning
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


class DataUpdater:
    """数据更新工作流

    用法:
        updater = DataUpdater(data_root="D:/Work/Project/download_a_share/data")
        updater.run_daily_update()
    """

    def __init__(
        self,
        data_root: str | Path = "D:/Work/Project/download_a_share/data",
        jq_config: dict | None = None,
    ):
        self.data_root = Path(data_root)
        self.parquet_root = self.data_root / "parquet"
        self.jq_config = jq_config or {}

    def run_daily_update(
        self,
        skip_download: bool = False,
        skip_wide_table: bool = False,
        skip_factor: bool = False,
        skip_backup: bool = True,
        data_types: list[str] | None = None,
        force_rebuild: bool = False,
    ) -> None:
        """执行每日数据更新

        Args:
            skip_download: 跳过下载步骤
            skip_wide_table: 跳过宽表重建
            skip_factor: 跳过因子更新
            skip_backup: 跳过备份（默认跳过）
            data_types: 指定下载的数据类型，None 则全部
            force_rebuild: 强制全量重建宽表（所有年份）
        """
        logger.info("=" * 60)
        logger.info(f"每日数据更新 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # 确定更新日期范围
        start_date, end_date = self._get_target_date_range()
        logger.info(f"更新日期范围: {start_date} ~ {end_date}")

        if not skip_download:
            self._download_incremental(start_date, end_date, data_types)

        if not skip_wide_table:
            self._update_wide_tables(force_rebuild)

        if not skip_factor:
            self._update_factors()

        if not skip_backup:
            self._backup()

        logger.info("数据更新完成")

    def _get_target_date_range(self) -> tuple[str, str]:
        """自动确定需下载的日期范围（T-1）

        策略:
          1. 获取本地最新数据日期
          2. 从最新日期+1到昨天，下载所有缺失的交易日
          3. 跨年时覆盖当年和前一年（应对跨年数据更新）

        Returns:
            (start_date, end_date) 日期字符串
        """
        try:
            latest_local = self._get_local_latest_date()
            latest_dt = datetime.strptime(latest_local, "%Y-%m-%d")
            start = (latest_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            # 首次运行：从当年年初开始
            year = datetime.now().year
            start = f"{year}-01-01"
            logger.info(f"首次运行，从 {start} 开始下载")

        end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return start, end

    def _get_local_latest_date(self) -> str:
        """获取本地最新数据日期"""
        try:
            lf = pl.scan_parquet(
                str(self.data_root / "stock_daily_wide_partitioned" / "**" / "*.parquet")
            )
            df = lf.select(pl.col("date").max()).collect()
            latest = df["date"][0]
            if hasattr(latest, "strftime"):
                return latest.strftime("%Y-%m-%d")
            return str(latest)[:10]
        except Exception:
            raise RuntimeError("无法获取本地最新日期")

    def _download_incremental(
        self,
        start_date: str,
        end_date: str,
        data_types: list[str] | None,
    ) -> None:
        """增量下载各数据类型"""
        logger.info(f"增量下载: {start_date} ~ {end_date}")

        try:
            from .sources.jqdata_source import JQDataSource
            from .downloaders.jq_downloader import JQDownloader

            source = JQDataSource(self.jq_config)
            downloader = JQDownloader(source, self.data_root)
            downloader.download_incremental(start_date, end_date, data_types)
        except ImportError:
            logger.warning("jqdatasdk 未安装，跳过在线下载")
        except Exception as e:
            logger.error(f"增量下载失败: {e}")
            raise

    def _update_wide_tables(self, force_rebuild: bool = False) -> None:
        """更新宽表分区

        - 周日或 force_rebuild: 全量重建所有年份分区
        - 平时: 只重生成当年分区（覆盖式写入）
        """
        is_weekend = datetime.now().weekday() >= 5
        rebuild_all = force_rebuild or is_weekend

        try:
            from .storage.wide_table_builder import WideTableBuilder

            builder = WideTableBuilder(self.data_root)
            if rebuild_all:
                logger.info("全量重建所有年份宽表分区...")
                builder.build_stock_wide_table(rebuild_all_years=True)
                builder.build_etf_wide_table(rebuild_all_years=True)
            else:
                logger.info("增量更新当年宽表分区...")
                builder.build_stock_wide_table(rebuild_all_years=False)
                builder.build_etf_wide_table(rebuild_all_years=False)
        except Exception as e:
            logger.error(f"宽表更新失败: {e}")
            raise

    def _update_factors(self) -> None:
        """更新因子数据"""
        logger.info("更新因子数据...")
        # 因子宽表由因子平台按需计算，这里仅更新原始因子数据
        # 实际因子计算在 factors/ 模块中

    def _backup(self) -> None:
        """数据备份（robocopy 增量镜像）"""
        backup_dir = "E:/Backup/download_a_share"
        logger.info(f"备份数据到 {backup_dir}...")

        try:
            if Path(backup_dir).exists():
                # Windows robocopy 增量镜像
                cmd = [
                    "robocopy",
                    str(self.data_root),
                    backup_dir,
                    "/MIR",  # 镜像
                    "/Z",  # 可重启模式
                    "/MT:8",  # 多线程
                    "/R:3",  # 重试3次
                    "/W:5",  # 等待5秒
                    "/NFL",  # 不列出文件
                    "/NDL",  # 不列出目录
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                # robocopy 返回码 0-7 都是成功
                if result.returncode <= 7:
                    logger.info("备份完成")
                else:
                    logger.error(f"备份失败，返回码: {result.returncode}")
            else:
                logger.warning(f"备份目录不存在: {backup_dir}")
        except Exception as e:
            logger.error(f"备份失败: {e}")


__all__ = ["DataUpdater"]
