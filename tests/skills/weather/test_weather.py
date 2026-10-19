"""The weather skill against mocked Open-Meteo responses (no live API calls)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from petbot.domain import EmptyResult, Platform, SkillContext, UpstreamUnavailable, User
from petbot.skills.weather.skill import FORECAST_URL, GEOCODE_URL, WeatherSkill
from petbot.types import WeatherArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


_PLACES: list[dict[str, Any]] = [
    {
        "name": "Paris",
        "latitude": 33.66,
        "longitude": -95.55,
        "admin1": "Texas",
        "country": "United States",
        "country_code": "US",
    },
    {
        "name": "Paris",
        "latitude": 48.85,
        "longitude": 2.35,
        "admin1": "Île-de-France",
        "country": "France",
        "country_code": "FR",
    },
]

_FORECAST: dict[str, Any] = {
    "timezone": "Europe/Paris",
    "current": {
        "time": "2026-10-19T05:30",
        "temperature_2m": 10.0,
        "apparent_temperature": 8.0,
        "relative_humidity_2m": 80,
        "weather_code": 3,
        "wind_speed_10m": 12.0,
    },
    "daily": {
        "time": ["2026-10-19", "2026-10-20"],
        "weather_code": [61, 0],
        "temperature_2m_max": [14.0, 16.0],
        "temperature_2m_min": [7.0, 6.0],
        "precipitation_probability_max": [70, 5],
    },
}


@respx.mock
async def test_weather_resolves_the_qualified_place_and_formats_both_units() -> None:
    respx.get(GEOCODE_URL).respond(json={"results": _PLACES})
    forecast = respx.get(FORECAST_URL).respond(json=_FORECAST)
    async with httpx.AsyncClient() as client:
        result = await WeatherSkill(client).run(WeatherArgs(location="Paris, France"), _ctx())
    params = forecast.calls.last.request.url.params
    assert params["latitude"] == "48.85" and params["timezone"] == "auto"
    assert result.text is not None
    assert "Paris, Île-de-France, France" in result.text
    assert "overcast, 10°C / 50°F" in result.text
    assert "2026-10-19: light rain, high 14°C / 57°F" in result.text
    assert "70% chance" in result.text


@respx.mock
async def test_weather_unqualified_place_takes_the_top_hit() -> None:
    respx.get(GEOCODE_URL).respond(json={"results": _PLACES})
    forecast = respx.get(FORECAST_URL).respond(json=_FORECAST)
    async with httpx.AsyncClient() as client:
        await WeatherSkill(client).run(WeatherArgs(location="Paris"), _ctx())
    assert forecast.calls.last.request.url.params["latitude"] == "33.66"


@respx.mock
async def test_weather_unknown_place_is_empty() -> None:
    respx.get(GEOCODE_URL).respond(json={})
    async with httpx.AsyncClient() as client:
        with pytest.raises(EmptyResult):
            await WeatherSkill(client).run(WeatherArgs(location="Nowhereville"), _ctx())


@respx.mock
async def test_weather_upstream_error_is_unavailable() -> None:
    respx.get(GEOCODE_URL).respond(status_code=503)
    async with httpx.AsyncClient() as client:
        with pytest.raises(UpstreamUnavailable):
            await WeatherSkill(client).run(WeatherArgs(location="Paris"), _ctx())


def test_pick_never_matches_a_qualifier_by_substring() -> None:
    from petbot.skills.weather.skill import _pick

    au = {"name": "Melbourne", "admin1": "Victoria", "country": "Australia", "country_code": "AU"}
    fl = {
        "name": "Melbourne",
        "admin1": "Florida",
        "country": "United States",
        "country_code": "US",
    }
    assert _pick([au, fl], "US") is fl
    assert _pick([au, fl], "FL") is fl
    assert _pick([au, fl], "Australia") is au
    assert _pick([fl, au], "Vic") is au  # a name's start still matches
    paris_fr = _PLACES[1]
    paris_tx = _PLACES[0]
    assert _pick([paris_fr, paris_tx], "TX") is paris_tx
    assert _pick([paris_fr, paris_tx], "Nowhere") is paris_fr  # no match: top hit
