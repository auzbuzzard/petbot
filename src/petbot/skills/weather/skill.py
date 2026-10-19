"""The ``weather`` skill: Open-Meteo geocoding + forecast (free, no key).

A place name resolves to coordinates, and the forecast is requested in the place's own
timezone, so the result also carries its local time. Temperatures come in °C with °F
alongside, so the answer suits whoever asks.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from petbot.domain import (
    EmptyResult,
    InvalidInput,
    Skill,
    SkillContext,
    SkillResult,
    UpstreamUnavailable,
)
from petbot.types import WeatherArgs

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: WMO weather interpretation codes, as Open-Meteo documents them.
_WMO: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    85: "light snow showers",
    86: "snow showers",
    95: "thunderstorm",
    96: "thunderstorm with light hail",
    99: "thunderstorm with hail",
}


def _describe(code: object) -> str:
    return _WMO.get(code, "unknown conditions") if isinstance(code, int) else "unknown conditions"


def _temp(celsius: object) -> str:
    if not isinstance(celsius, int | float):
        return "?"
    return f"{celsius:.0f}°C / {celsius * 9 / 5 + 32:.0f}°F"


def _pick(results: list[dict[str, Any]], qualifier: str) -> dict[str, Any]:
    """The geocoding hit matching the place's qualifier ("WA", "France"), else the top hit."""
    q = qualifier.lower()
    if q:
        for r in results:
            fields = (r.get("admin1", ""), r.get("country", ""), r.get("country_code", ""))
            if any(q == str(f).lower() or q in str(f).lower() for f in fields if f):
                return r
    return results[0]


def _place_name(place: dict[str, Any]) -> str:
    parts = (place.get("name"), place.get("admin1"), place.get("country"))
    return ", ".join(dict.fromkeys(str(p) for p in parts if p))


def format_forecast(place: dict[str, Any], data: dict[str, Any]) -> str:
    """The forecast summary handed to the model."""
    current = data.get("current", {})
    lines = [
        f"Weather for {_place_name(place)} (local time {current.get('time', '?')}, "
        f"{data.get('timezone', '?')}):",
        f"- Now: {_describe(current.get('weather_code'))}, "
        f"{_temp(current.get('temperature_2m'))} "
        f"(feels like {_temp(current.get('apparent_temperature'))}), "
        f"humidity {current.get('relative_humidity_2m', '?')}%, "
        f"wind {current.get('wind_speed_10m', '?')} km/h.",
    ]
    daily = data.get("daily", {})
    for i, day in enumerate(daily.get("time", [])):

        def at(key: str, i: int = i) -> object:
            values = daily.get(key, [])
            return values[i] if i < len(values) else None

        lines.append(
            f"- {day}: {_describe(at('weather_code'))}, "
            f"high {_temp(at('temperature_2m_max'))}, low {_temp(at('temperature_2m_min'))}, "
            f"{at('precipitation_probability_max') or 0}% chance of precipitation."
        )
    return "\n".join(lines)


class WeatherSkill(Skill[WeatherArgs]):
    """Current conditions and a short forecast for a named place."""

    name = "weather"
    description = "Get the weather for a place."
    args_model = WeatherArgs

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("weather: %s failed: %s", url, type(exc).__name__)
            raise UpstreamUnavailable("The weather service isn't answering right now.") from exc
        return body

    async def run(self, args: WeatherArgs, ctx: SkillContext) -> SkillResult:
        name, _, qualifier = (part.strip() for part in args.location.partition(","))
        if not name:
            raise InvalidInput("Which place should I check the weather for?")
        found = await self._get(
            GEOCODE_URL, {"name": name, "count": 5, "language": "en", "format": "json"}
        )
        results = found.get("results") or []
        if not results:
            raise EmptyResult(f"I couldn't find a place called {args.location!r}.")
        place = _pick(results, qualifier)
        data = await self._get(
            FORECAST_URL,
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )
        return SkillResult.message(format_forecast(place, data))
