"""
Application entrypoint.

定时任务每天 14:00 启动 Docker 容器后，将执行本模块的 main()：
1. 读取环境变量 FEISHU_WEBHOOK_URL
2. 计算前一天日期
3. 爬取该日期的每日 AI 资讯
4. 格式化为文本（《每日最新AI资讯》...）
5. 通过飞书自定义机器人发送消息
6. 若设置了 OPENCLAW_MESSAGE_FILE，将同一份内容写入该路径，供宿主机 cron 用 OpenClaw CLI 推到 QQ 小龙虾
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

from .ai_news.crawler import AiNewsItem, fetch_daily_news
from .ai_news.formatter import format_news_list
from .common.feishu import send_text


def configure_logging() -> None:
    """配置基础日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def get_target_date(today: date | None = None) -> date:
    """
    根据当前日期计算目标日期（前一天）。

    :param today: 可选的“今天”日期，主要方便将来做单元测试；不传则使用系统当前日期。
    """
    if today is None:
        today = datetime.now().date()
    return today - timedelta(days=1)


def main() -> None:
    """每日 AI 资讯主流程入口。"""
    # 先加载 .env（若存在），将其中的键值写入环境变量。
    # 默认会在当前工作目录查找 .env，适合本项目的运行方式。
    load_dotenv()

    configure_logging()
    logger = logging.getLogger(__name__)

    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Environment variable FEISHU_WEBHOOK_URL is not set. Abort.")
        return

    target_date = get_target_date()
    logger.info("Starting daily AI news job for date: %s", target_date.isoformat())

    items: list[AiNewsItem] = fetch_daily_news(target_date)
    content = format_news_list(items, target_date)

    send_text(webhook_url, content)

    # 可选：写入文件供 OpenClaw 定时推送（方案 A：宿主机 cron 读此文件后调 openclaw message send）
    message_file = os.environ.get("OPENCLAW_MESSAGE_FILE")
    if message_file:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(message_file)) or ".", exist_ok=True)
            with open(message_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Content written to OPENCLAW_MESSAGE_FILE: %s", message_file)
        except OSError as e:
            logger.warning("Failed to write OPENCLAW_MESSAGE_FILE %s: %s", message_file, e)

    logger.info("Daily AI news job finished.")


if __name__ == "__main__":
    main()



