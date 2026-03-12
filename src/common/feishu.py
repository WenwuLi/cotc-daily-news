"""
Feishu webhook client.

封装飞书自定义机器人 Webhook 的发送逻辑，对上层只暴露一个简单的文本发送接口。
"""

from __future__ import annotations

import logging
from typing import Final

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: Final[float] = 5.0


def send_text(webhook_url: str, content: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
    """
    通过飞书自定义机器人 Webhook 发送纯文本消息。

    :param webhook_url: 飞书机器人 Webhook 地址（从环境变量 FEISHU_WEBHOOK_URL 读取）
    :param content: 要发送的纯文本内容
    :param timeout: HTTP 请求超时时间（秒）
    """
    if not webhook_url:
        logger.error("Feishu webhook URL is empty, skip sending message.")
        return

    payload = {
        "msg_type": "text",
        "content": {"text": content},
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to send message to Feishu: %s", exc)
        return

    try:
        data = resp.json()
    except ValueError:
        logger.warning("Feishu response is not valid JSON: %s", resp.text)
        return

    code = data.get("code")
    if code not in (0, None):
        logger.error("Feishu returned error code %s: %s", code, data)
    else:
        logger.info("Message sent to Feishu successfully.")


