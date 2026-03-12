"""
Crawler for daily AI news from https://ai-bot.cn/daily-ai-news/.

基于页面的日期分组结构，从列表页中解析出前一天的快讯列表。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import List

import requests
from bs4 import BeautifulSoup

from .config import BASE_URL, MAX_ITEMS

logger = logging.getLogger(__name__)


@dataclass
class AiNewsItem:
    """
    表示一条 AI 资讯。

    属性:
        title: 标题文本
        summary: 摘要
        date_label: 页面上的日期标签（例如「3月11·周三」）
        source: 来源（例如「机器之心」），若无法解析可为空字符串
        url: 详情页完整 URL
    """

    title: str
    summary: str
    date_label: str
    source: str
    url: str


def fetch_daily_news(target_date: date) -> List[AiNewsItem]:
    """
    抓取指定日期的每日 AI 资讯。

    :param target_date: 目标日期（通常为今天减一天）
    :return: 资讯列表，最多 MAX_ITEMS 条；若页面无该日期分组则返回空列表。
    """
    logger.info("Fetching AI daily news for date: %s", target_date.isoformat())

    try:
        resp = requests.get(BASE_URL, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch ai-bot daily page: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # 由于我们无法在设计阶段精确依赖 DOM 结构，这里采用较为宽松的匹配策略：
    # 1. 先尝试根据日期字符串（例如「3月11」）定位对应分组标题。
    # 2. 再从该分组下方收集若干条目。
    target_group = _find_date_group(soup, target_date)
    if target_group is None:
        logger.warning("No group found for date %s on ai-bot page.", target_date.isoformat())
        return []

    items = _parse_items_from_group(target_group, max_items=MAX_ITEMS)
    logger.info("Parsed %d news items for date %s", len(items), target_date.isoformat())
    return items


def _find_date_group(soup: BeautifulSoup, target_date: date):
    """
    在页面中查找对应日期分组的根节点。

    备注：具体 DOM 结构可能会有变化，此函数应尽量写得健壮，
    找不到时返回 None，由上层逻辑处理为「无数据」。
    """
    # 假设页面日期标签形如「3月11·周三」，这里先构造「3月11」的前缀字符串。
    date_prefix = f"{target_date.month}月{target_date.day}"

    # 常见实现中，日期标题可能在 h2/h3 或带特定 class 的元素中，
    # 此处采用笼统搜索，后续可根据实际页面结构再优化选择器。
    for heading_tag in ("h1", "h2", "h3", "h4", "div", "span"):
        candidates = soup.find_all(heading_tag)
        for node in candidates:
            text = (node.get_text() or "").strip()
            if text.startswith(date_prefix):
                # 这里假设资讯条目位于该标题之后的某个容器中，
                # 可以是父节点或紧邻的兄弟节点，根据实际结构再调整。
                parent = node.parent
                return parent

    return None


def _parse_items_from_group(group_node, *, max_items: int) -> List[AiNewsItem]:
    """
    从单个日期分组节点中解析资讯条目。

    该实现对 DOM 结构做了尽量宽松的假设，保证即便页面有轻微变动也能解析出主要内容。
    """
    items: List[AiNewsItem] = []

    # 典型结构可能是 group_node 内部存在若干 article/li/div 子节点，对应每条资讯。
    # 这里先寻找常见的子容器标签。
    candidate_tags = ("article", "li", "div")
    for tag in candidate_tags:
        for node in group_node.find_all(tag, recursive=True):
            if len(items) >= max_items:
                return items

            # 尝试从子节点中提取标题、链接、摘要和来源等信息。
            title_link = node.find("a")
            title = (title_link.get_text() or "").strip() if title_link else ""
            href = title_link.get("href") if title_link else ""

            # 摘要：常见为 <p> 标签或带特定 class 的段落。
            summary_node = node.find("p")
            summary = (summary_node.get_text() or "").strip() if summary_node else ""

            # 来源：可能出现在包含“来源”二字的文本中。
            source = ""
            text = (node.get_text() or "").strip()
            if "来源" in text:
                # 简单从文本中切分提取，后续可根据实际结构增强。
                # 例如 "来源：机器之心" -> "机器之心"
                after = text.split("来源", 1)[-1]
                after = after.lstrip("：:").strip()
                # 只取第一行/第一段
                source = after.splitlines()[0].strip()

            if not title and not summary:
                # 噪声节点，忽略
                continue

            # 日期标签从 group_node 的文本中整体提取一次更合适，
            # 但为简化，这里直接使用 group_node 的第一行文本作为 date_label。
            group_text = (group_node.get_text() or "").strip()
            date_label = group_text.splitlines()[0].strip() if group_text else ""

            # 将相对链接补全为绝对链接（若需要）。
            url = href or ""
            if url and url.startswith("/"):
                url = BASE_URL.rstrip("/") + url

            item = AiNewsItem(
                title=title,
                summary=summary,
                date_label=date_label,
                source=source,
                url=url,
            )
            items.append(item)

    return items


