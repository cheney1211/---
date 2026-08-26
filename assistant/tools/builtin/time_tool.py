"""
Current time tool.

Returns the current date and time in a human-readable format.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from ..base import Tool
from ..registry import register

# China Standard Time (UTC+8)
_CST = timezone(timedelta(hours=8))


class CurrentTimeTool(Tool):
    name: str = "get_current_time"
    description: str = "获取当前的日期和时间（北京时间）。"

    def _run(self) -> str:
        now = datetime.now(_CST)
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[now.weekday()]
        return f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} {weekday} (北京时间)"


register(CurrentTimeTool())
