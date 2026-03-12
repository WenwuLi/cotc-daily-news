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

昨日（2026-03-10）暂无可用的 AI 资讯数据。
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, List

from .crawler import AiNewsItem


TITLE_LINE = "《每日最新AI资讯》"


def format_news_list(items: Iterable[AiNewsItem], target_date: date) -> str:
    """
    将 AI 资讯列表格式化为飞书要发送的纯文本。

    :param items: 资讯条目可迭代对象
    :param target_date: 目标日期（通常为昨天），用于生成「时间：YYYY-MM-DD」行
    :return: 纯文本内容
    """
    items_list: List[AiNewsItem] = list(items)
    date_iso = target_date.isoformat()

    if not items_list:
        # 无数据场景：仍然推送简要提示消息
        lines = [
            TITLE_LINE,
            "",
            f"昨日（{date_iso}）暂无可用的 AI 资讯数据。",
        ]
        return "\n".join(lines)

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


