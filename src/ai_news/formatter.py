"""
Formatter for AI daily news content.

根据爬取的资讯列表，生成符合飞书推送需求的纯文本内容。

目标格式示例（有数据时）：

《每日最新AI资讯》

1. 标题A
摘要A
时间：2026-03-10
https://example.com/a

2. 标题B
摘要B
时间：2026-03-10
https://example.com/b

...

无数据时示例：

《每日最新AI资讯》

暂无可用的 AI 资讯数据。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable, List

from .crawler import AiNewsItem


TITLE_LINE = "《每日最新AI资讯》"

_LABEL_MD_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def _month_day_from_date_label(label: str) -> tuple[int, int] | None:
    m = _LABEL_MD_RE.search(label or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _infer_calendar_date(month: int, day: int, ref: date) -> date:
    """根据月、日及参考日期推断公历日期（处理跨年等边界）。"""
    y = ref.year
    try:
        d = date(y, month, day)
    except ValueError:
        return ref
    if d - ref > timedelta(days=31):
        try:
            return date(y - 1, month, day)
        except ValueError:
            return ref
    if ref - d > timedelta(days=366):
        try:
            return date(y + 1, month, day)
        except ValueError:
            return ref
    return d


def _issue_display_date(items: List[AiNewsItem], ref: date) -> date:
    """从条目上的页面日期标签推断用于展示的公历日期。"""
    for item in items:
        md = _month_day_from_date_label(item.date_label)
        if md:
            return _infer_calendar_date(md[0], md[1], ref)
    return ref


def format_news_list(items: Iterable[AiNewsItem], *, reference_date: date | None = None) -> str:
    """
    将 AI 资讯列表格式化为飞书要发送的纯文本。

    :param items: 资讯条目可迭代对象
    :param reference_date: 用于从「M月D日」标签推断公历年的参考日，默认当天
    :return: 纯文本内容
    """
    items_list: List[AiNewsItem] = list(items)
    ref = reference_date or date.today()

    if not items_list:
        # 无数据场景：仍然推送简要提示消息
        lines = [
            TITLE_LINE,
            "",
            "暂无可用的 AI 资讯数据。",
        ]
        return "\n".join(lines)

    date_iso = _issue_display_date(items_list, ref).isoformat()

    lines: List[str] = [TITLE_LINE, ""]

    for idx, item in enumerate(items_list, start=1):
        lines.append(f"{idx}. {item.title}")
        lines.append(item.summary)
        lines.append(f"时间：{date_iso}")
        lines.append(item.url)
        lines.append("")  # 条目间空行

    # 去掉末尾可能多余的空行
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


