"""
Crawler for daily AI news from https://ai-bot.cn/daily-ai-news/.

基于页面的日期分组结构解析列表页；主流程使用「最新一期」（DOM 中第一个 news-date 区块），
亦保留按指定日期抓取的 `fetch_daily_news` 供测试或回退。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Set

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from .config import BASE_URL, MAX_ITEMS

logger = logging.getLogger(__name__)

# 站点对默认的 python-requests User-Agent 常返回 403；使用常见浏览器头降低被拒概率。
# 可通过环境变量 AI_NEWS_HTTP_USER_AGENT 覆盖（例如与本地浏览器一致）。
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# 解析树异常时，日期块所在的 div 可能被挂到 img 等空元素下；不能把这类父节点当作分组根。
_BAD_GROUP_PARENT_NAMES: frozenset[str] = frozenset(
    {"area", "br", "embed", "hr", "img", "input", "link", "meta", "source", "track"}
)


def _request_headers() -> Dict[str, str]:
    ua = os.environ.get("AI_NEWS_HTTP_USER_AGENT", "").strip() or _DEFAULT_USER_AGENT
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": BASE_URL,
    }


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


def _fetch_soup() -> BeautifulSoup | None:
    """拉取列表页并解析为 BeautifulSoup；失败时返回 None。"""
    try:
        resp = requests.get(BASE_URL, headers=_request_headers(), timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch ai-bot daily page: %s", exc)
        return None
    return BeautifulSoup(resp.text, "html.parser")


def fetch_latest_daily_news() -> List[AiNewsItem]:
    """
    抓取列表页上「最新一期」资讯（文档顺序下第一个 div.news-date 及其后同级 news-item）。

    若该日期块无条目，则依次尝试后续 news-date 块，直到有数据或耗尽。
    """
    logger.info("Fetching latest AI daily news issue from ai-bot page.")

    soup = _fetch_soup()
    if soup is None:
        return []

    anchors = soup.find_all("div", class_=lambda c: bool(c) and "news-date" in c)
    for anchor in anchors:
        items = _parse_news_items_after_date_anchor(anchor, max_items=MAX_ITEMS)
        if items:
            label = (anchor.get_text() or "").strip()
            logger.info("Parsed %d news items for latest issue (%s)", len(items), label)
            return items

    logger.warning("No news items found in any news-date section on ai-bot page.")
    return []


def fetch_daily_news(target_date: date) -> List[AiNewsItem]:
    """
    抓取指定日期的每日 AI 资讯。

    :param target_date: 目标日期（通常为今天减一天）
    :return: 资讯列表，最多 MAX_ITEMS 条；若页面无该日期分组则返回空列表。
    """
    logger.info("Fetching AI daily news for date: %s", target_date.isoformat())

    soup = _fetch_soup()
    if soup is None:
        return []

    # 由于我们无法在设计阶段精确依赖 DOM 结构，这里采用较为宽松的匹配策略：
    # 1. 先尝试根据日期字符串（例如「3月11」）定位对应分组标题。
    # 2. 再从该分组下方收集若干条目。
    anchor = _find_news_date_anchor(soup, target_date)
    if anchor is not None:
        items = _parse_news_items_after_date_anchor(anchor, max_items=MAX_ITEMS)
    else:
        target_group = _find_date_group_loose(soup, target_date)
        if target_group is None:
            logger.warning("No group found for date %s on ai-bot page.", target_date.isoformat())
            return []
        items = _parse_items_from_group(target_group, max_items=MAX_ITEMS)
    logger.info("Parsed %d news items for date %s", len(items), target_date.isoformat())
    return items


def _find_news_date_anchor(soup: BeautifulSoup, target_date: date) -> Tag | None:
    """
    ai-bot.cn：每日块以 div.news-date 开头，同级后续为若干 div.news-item，再嵌套下一日的 div.news-list。

    不能用外层 div.news-list 作为分组根（整页只有一个大容器，内含多日）。
    """
    date_prefix = f"{target_date.month}月{target_date.day}"
    for el in soup.find_all("div", class_=lambda c: bool(c) and "news-date" in c):
        text = (el.get_text() or "").strip()
        if text.startswith(date_prefix):
            return el
    return None


def _parse_news_items_after_date_anchor(news_date_el: Tag, *, max_items: int) -> List[AiNewsItem]:
    """从 div.news-date 起，只解析其后同级区块内的条目，遇到下一日容器即停止。"""
    parent = news_date_el.parent
    if parent is None:
        return []

    date_label = (news_date_el.get_text() or "").strip()
    items: List[AiNewsItem] = []
    seen_urls: Set[str] = set()
    seen_fingerprints: Set[tuple[str, str]] = set()
    passed_anchor = False

    for child in parent.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue
        if child is news_date_el:
            passed_anchor = True
            continue
        if not passed_anchor:
            continue

        cls = child.get("class") or []
        if "news-list" in cls:
            break
        if "news-date" in cls:
            break
        if "news-item" not in cls:
            continue

        item = _item_from_news_node(child, date_label=date_label)
        if item is None:
            continue

        if item.url:
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
        else:
            fp = (item.title, item.summary)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)

        items.append(item)
        if len(items) >= max_items:
            break

    return items


def _item_from_news_node(node: Tag, *, date_label: str) -> AiNewsItem | None:
    """从单条资讯根节点（如 div.news-item）抽取字段。"""
    title_link = node.find("a")
    title = (title_link.get_text() or "").strip() if title_link else ""
    href = title_link.get("href") if title_link else ""

    summary_node = node.find("p")
    summary = (summary_node.get_text() or "").strip() if summary_node else ""

    source = ""
    text = (node.get_text() or "").strip()
    if "来源" in text:
        after = text.split("来源", 1)[-1]
        after = after.lstrip("：:").strip()
        source = after.splitlines()[0].strip()

    if not title and not summary:
        return None

    url = href or ""
    if url and url.startswith("/"):
        url = BASE_URL.rstrip("/") + url

    return AiNewsItem(
        title=title,
        summary=summary,
        date_label=date_label,
        source=source,
        url=url,
    )


def _group_root_for_date_node(node) -> object:
    """
    选择用于向下遍历的「日期分组」根节点。

    站点上常见为日期标题的父级包含后续条目；但若父级是 img 等（Broken HTML / 解析树异常），
    应退回使用当前节点，否则会扫到整页其它日期块并产生重复条目。
    """
    parent = getattr(node, "parent", None)
    if parent is None:
        return node
    name = getattr(parent, "name", None)
    if name in _BAD_GROUP_PARENT_NAMES:
        return node
    return parent


def _find_date_group_loose(soup: BeautifulSoup, target_date: date):
    """
    在页面中查找对应日期分组的根节点（宽松策略，供无 news-date 结构时回退）。

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
                return _group_root_for_date_node(node)

    return None


def _parse_items_from_group(group_node, *, max_items: int) -> List[AiNewsItem]:
    """
    从单个日期分组节点中解析资讯条目。

    该实现对 DOM 结构做了尽量宽松的假设，保证即便页面有轻微变动也能解析出主要内容。
    """
    items: List[AiNewsItem] = []
    seen_urls: Set[str] = set()
    seen_fingerprints: Set[tuple[str, str]] = set()

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

            # 将相对链接补全为绝对链接（若需要）。
            url = href or ""
            if url and url.startswith("/"):
                url = BASE_URL.rstrip("/") + url

            # 嵌套 div / 多标签命中同一条时去重
            if url:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
            else:
                fp = (title, summary)
                if fp in seen_fingerprints:
                    continue
                seen_fingerprints.add(fp)

            # 日期标签从 group_node 的文本中整体提取一次更合适，
            # 但为简化，这里直接使用 group_node 的第一行文本作为 date_label。
            group_text = (group_node.get_text() or "").strip()
            date_label = group_text.splitlines()[0].strip() if group_text else ""

            items.append(
                AiNewsItem(
                    title=title,
                    summary=summary,
                    date_label=date_label,
                    source=source,
                    url=url,
                )
            )

    return items


