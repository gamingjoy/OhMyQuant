"""集成模块

提供与外部系统的集成功能：
  - 数据 API 客户端（Tushare、AkShare、Baostock）
  - 交易 API 客户端（模拟交易、实盘交易）
  - 通知客户端（邮件、钉钉、飞书）
  - 数据同步器（本地与远程数据同步）

用法：
    from ohmyquant.integration import DataAPIClient, TradingAPIClient, NotificationClient, DataSync

    data_client = DataAPIClient(provider="tushare")
    trading_client = TradingAPIClient(broker="simulated")
    notifier = NotificationClient(channels=["dingtalk"])
    sync = DataSync()
"""
from .api_client import DataAPIClient, NotificationClient, TradingAPIClient
from .data_sync import DataSync, SyncTask

__all__ = [
    # API 客户端
    "DataAPIClient",
    "TradingAPIClient",
    "NotificationClient",
    # 数据同步
    "DataSync",
    "SyncTask",
]
