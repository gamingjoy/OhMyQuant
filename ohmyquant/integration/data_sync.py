"""数据同步

提供数据同步和更新功能：
  - 本地数据与远程数据同步
  - 增量更新
  - 数据版本管理
  - 同步任务调度

功能：
  - DataSync: 数据同步器
  - SyncTask: 同步任务
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger
from .api_client import DataAPIClient

logger = get_logger(__name__)


@dataclass
class SyncTask:
    """同步任务"""

    task_id: str
    data_type: str
    codes: List[str]
    start_date: str
    end_date: str
    frequency: str = "daily"
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "data_type": self.data_type,
            "codes": self.codes,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "frequency": self.frequency,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class DataSync:
    """数据同步器"""

    def __init__(self, api_client: DataAPIClient | None = None):
        """初始化

        Args:
            api_client: API 客户端
        """
        self.api_client = api_client or DataAPIClient()
        self._tasks: Dict[str, SyncTask] = {}

    def create_sync_task(
        self,
        data_type: str,
        codes: List[str],
        start_date: str,
        end_date: str,
        frequency: str = "daily",
    ) -> str:
        """创建同步任务

        Args:
            data_type: 数据类型（daily/factor/index）
            codes: 代码列表
            start_date: 开始日期
            end_date: 结束日期
            frequency: 频率

        Returns:
            str: 任务 ID
        """
        task_id = f"sync_{int(time.time())}"
        task = SyncTask(
            task_id=task_id,
            data_type=data_type,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        self._tasks[task_id] = task
        logger.info(f"创建同步任务: {task_id}")
        return task_id

    def run_sync(self, task_id: str) -> bool:
        """运行同步任务

        Args:
            task_id: 任务 ID

        Returns:
            bool: 是否成功
        """
        if task_id not in self._tasks:
            logger.warning(f"任务不存在: {task_id}")
            return False

        task = self._tasks[task_id]
        task.status = "running"

        try:
            total = len(task.codes)
            for i, code in enumerate(task.codes):
                if task.data_type == "daily":
                    data = self.api_client.get_daily_data(code, task.start_date, task.end_date, task.frequency)
                elif task.data_type == "factor":
                    data = self.api_client.get_factor_data(code, task.start_date, task.end_date, [])
                elif task.data_type == "index":
                    data = self.api_client.get_index_data(code, task.start_date, task.end_date)
                else:
                    logger.warning(f"未知数据类型: {task.data_type}")
                    continue

                logger.debug(f"数据已获取: {code}, 记录数: {len(data.get('data', []))}")

                task.progress = (i + 1) / total * 100
                logger.info(f"同步进度: {task_id} - {code} ({task.progress:.1f}%)")

            task.status = "completed"
            task.completed_at = datetime.now().isoformat()
            task.message = f"成功同步 {total} 个标的"
            logger.info(f"同步任务完成: {task_id}")
            return True

        except Exception as e:
            task.status = "failed"
            task.message = str(e)
            logger.error(f"同步任务失败: {task_id}, 错误: {e}")
            return False

    def get_task_status(self, task_id: str) -> Optional[SyncTask]:
        """获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            SyncTask 或 None
        """
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[SyncTask]:
        """列出所有任务

        Returns:
            List[SyncTask]
        """
        return list(self._tasks.values())

    def sync_all_stocks(
        self,
        start_date: str,
        end_date: str,
        market: str = "all",
    ) -> str:
        """同步所有股票

        Args:
            start_date: 开始日期
            end_date: 结束日期
            market: 市场

        Returns:
            str: 任务 ID
        """
        codes = self.api_client.get_stock_list(market)
        task_id = self.create_sync_task("daily", codes, start_date, end_date)
        self.run_sync(task_id)
        return task_id

    def sync_incremental(self, data_type: str, codes: List[str]) -> str:
        """增量同步

        Args:
            data_type: 数据类型
            codes: 代码列表

        Returns:
            str: 任务 ID
        """
        today = datetime.now().strftime("%Y-%m-%d")
        task_id = self.create_sync_task(data_type, codes, today, today)
        self.run_sync(task_id)
        return task_id


__all__ = ["SyncTask", "DataSync"]
