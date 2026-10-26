"""The ``weather`` skill package (Open-Meteo; no credentials)."""

from __future__ import annotations

import httpx

from petbot.skills.weather.skill import WeatherSkill

__all__ = ["WeatherSkill", "build_weather"]


def build_weather() -> WeatherSkill:
    return WeatherSkill(client=httpx.AsyncClient(timeout=10.0))
