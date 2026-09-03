"""
天气查询工具。

使用免费的 wttr.in API（无需 API 密钥）。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register


class WeatherInput(BaseModel):
    """get_weather 的输入模式。"""
    city: str = Field(description="城市名称，如 'Beijing'、'Shanghai'、'New York'")


class WeatherTool(Tool):
    name: str = "get_weather"
    description: str = "获取指定城市的当前天气信息（温度、天气状况、湿度）。"
    args_schema: Type[BaseModel] = WeatherInput

    def _run(self, city: str) -> str:
        try:
            encoded = urllib.parse.quote(city)
            url = f"https://wttr.in/{encoded}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.64.1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            current = data["current_condition"][0]
            temp = current["temp_C"]
            desc = current["weatherDesc"][0]["value"]
            humidity = current["humidity"]
            feels_like = current["FeelsLikeC"]
            return (
                f"{city} 当前天气: {desc}, "
                f"温度 {temp}°C (体感 {feels_like}°C), "
                f"湿度 {humidity}%"
            )
        except Exception as e:
            return f"获取 '{city}' 天气失败: {e}"


register(WeatherTool())
