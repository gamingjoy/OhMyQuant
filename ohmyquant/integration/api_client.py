"""API 客户端

提供与外部数据平台的 API 交互：
  - 数据源 API（Tushare、AkShare、Baostock）
  - 交易 API（模拟交易、实盘交易）
  - 通知 API（邮件、钉钉、飞书）

功能：
  - DataAPIClient: 数据 API 客户端
  - TradingAPIClient: 交易 API 客户端
  - NotificationClient: 通知客户端
"""
from __future__ import annotations

import json
import os
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import requests

from ..core.logging import get_logger

logger = get_logger(__name__)


class DataAPIClient:
    """数据 API 客户端"""

    def __init__(self, provider: str = "tushare", config: Dict[str, Any] | None = None):
        """初始化

        Args:
            provider: 数据提供商（tushare/akshare/baostock）
            config: API 配置
        """
        self.provider = provider
        self.config = config or {}
        self._session = requests.Session()

    def get_stock_list(self, market: str = "all") -> list:
        """获取股票列表

        Args:
            market: 市场（all/sh/sz）

        Returns:
            list: 股票代码列表
        """
        logger.info(f"获取股票列表: {self.provider}, {market}")
        return []

    def get_daily_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        freq: str = "daily",
    ) -> Dict[str, Any]:
        """获取日线数据

        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            freq: 频率（daily/weekly/monthly）

        Returns:
            Dict: 数据字典
        """
        logger.info(f"获取日线数据: {code}, {start_date} ~ {end_date}")
        return {"code": code, "data": []}

    def get_factor_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        factors: list[str],
    ) -> Dict[str, Any]:
        """获取因子数据

        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            factors: 因子列表

        Returns:
            Dict: 因子数据字典
        """
        logger.info(f"获取因子数据: {code}, {factors}")
        return {"code": code, "factors": factors, "data": []}

    def get_index_data(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """获取指数数据

        Args:
            index_code: 指数代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict: 指数数据字典
        """
        logger.info(f"获取指数数据: {index_code}")
        return {"code": index_code, "data": []}


class TradingAPIClient:
    """交易 API 客户端"""

    def __init__(self, broker: str = "simulated", config: Dict[str, Any] | None = None):
        """初始化

        Args:
            broker: 券商/交易平台（simulated/ctp/ths）
            config: 交易配置
        """
        self.broker = broker
        self.config = config or {}
        self._positions: Dict[str, float] = {}
        self._cash: float = 1000000.0

    def login(self) -> bool:
        """登录

        Returns:
            bool: 是否成功
        """
        logger.info(f"登录交易系统: {self.broker}")
        return True

    def get_positions(self) -> Dict[str, float]:
        """获取持仓

        Returns:
            Dict: {股票代码: 持仓数量}
        """
        return self._positions

    def get_cash(self) -> float:
        """获取现金

        Returns:
            float: 现金余额
        """
        return self._cash

    def buy(self, code: str, price: float, quantity: int) -> Dict[str, Any]:
        """买入

        Args:
            code: 股票代码
            price: 价格
            quantity: 数量

        Returns:
            Dict: 交易结果
        """
        cost = price * quantity
        if cost > self._cash:
            logger.warning(f"现金不足: {self._cash:.2f} < {cost:.2f}")
            return {"success": False, "message": "现金不足"}

        self._cash -= cost
        self._positions[code] = self._positions.get(code, 0) + quantity
        logger.info(f"买入: {code}, {quantity}股 @ {price:.2f}")

        return {
            "success": True,
            "code": code,
            "price": price,
            "quantity": quantity,
            "cost": cost,
        }

    def sell(self, code: str, price: float, quantity: int) -> Dict[str, Any]:
        """卖出

        Args:
            code: 股票代码
            price: 价格
            quantity: 数量

        Returns:
            Dict: 交易结果
        """
        if self._positions.get(code, 0) < quantity:
            logger.warning(f"持仓不足: {self._positions.get(code, 0)} < {quantity}")
            return {"success": False, "message": "持仓不足"}

        revenue = price * quantity
        self._cash += revenue
        self._positions[code] -= quantity
        if self._positions[code] == 0:
            del self._positions[code]

        logger.info(f"卖出: {code}, {quantity}股 @ {price:.2f}")

        return {
            "success": True,
            "code": code,
            "price": price,
            "quantity": quantity,
            "revenue": revenue,
        }

    def close_all(self) -> Dict[str, Any]:
        """平仓全部

        Returns:
            Dict: 平仓结果
        """
        logger.info("平仓全部")
        self._positions.clear()
        return {"success": True, "message": "已平仓全部"}


class NotificationClient:
    """通知客户端"""

    def __init__(self, channels: list[str] = None, config: Dict[str, Any] | None = None):
        """初始化

        Args:
            channels: 通知渠道（email/dingtalk/feishu）
            config: 通知配置
        """
        self.channels = channels or ["email"]
        self.config = config or {}

    def send_email(self, subject: str, content: str, to: str | list[str]) -> bool:
        """发送邮件

        Args:
            subject: 主题
            content: 内容
            to: 收件人

        Returns:
            bool: 是否成功
        """
        try:
            smtp_server = self.config.get("smtp_server", "smtp.gmail.com")
            smtp_port = self.config.get("smtp_port", 587)
            username = self.config.get("smtp_username", "")
            password = self.config.get("smtp_password", "")

            msg = MIMEText(content, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = username
            msg["To"] = ",".join(to) if isinstance(to, list) else to

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.sendmail(username, to, msg.as_string())

            logger.info(f"邮件已发送: {to}")
            return True
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False

    def send_dingtalk(self, content: str, webhook: str | None = None) -> bool:
        """发送钉钉消息

        Args:
            content: 内容
            webhook: webhook 地址

        Returns:
            bool: 是否成功
        """
        try:
            url = webhook or self.config.get("dingtalk_webhook", "")
            if not url:
                logger.warning("钉钉 webhook 未配置")
                return False

            data = {"msgtype": "text", "text": {"content": content}}
            response = requests.post(url, json=data)

            if response.status_code == 200:
                logger.info("钉钉消息已发送")
                return True
            else:
                logger.error(f"钉钉消息发送失败: {response.text}")
                return False
        except Exception as e:
            logger.error(f"钉钉消息发送失败: {e}")
            return False

    def send_feishu(self, content: str, webhook: str | None = None) -> bool:
        """发送飞书消息

        Args:
            content: 内容
            webhook: webhook 地址

        Returns:
            bool: 是否成功
        """
        try:
            url = webhook or self.config.get("feishu_webhook", "")
            if not url:
                logger.warning("飞书 webhook 未配置")
                return False

            data = {"msg_type": "text", "content": {"text": content}}
            response = requests.post(url, json=data)

            if response.status_code == 200:
                logger.info("飞书消息已发送")
                return True
            else:
                logger.error(f"飞书消息发送失败: {response.text}")
                return False
        except Exception as e:
            logger.error(f"飞书消息发送失败: {e}")
            return False

    def send(self, subject: str, content: str, to: str | list[str] | None = None) -> Dict[str, bool]:
        """发送通知（多渠道）

        Args:
            subject: 主题
            content: 内容
            to: 收件人（仅 email 使用）

        Returns:
            Dict: {渠道: 是否成功}
        """
        results = {}
        for channel in self.channels:
            if channel == "email":
                results["email"] = self.send_email(subject, content, to or [])
            elif channel == "dingtalk":
                results["dingtalk"] = self.send_dingtalk(content)
            elif channel == "feishu":
                results["feishu"] = self.send_feishu(content)

        return results


__all__ = ["DataAPIClient", "TradingAPIClient", "NotificationClient"]
