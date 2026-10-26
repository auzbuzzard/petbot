"""The web skills' own configuration.

Tavily is the keyed primary search provider; with no key the search skill runs on the
keyless ``ddgs`` fallback alone, so a dev checkout needs no secret.
"""

from __future__ import annotations

from importlib.metadata import version

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = f"PetBot/{version('petbot')} (https://github.com/auzbuzzard/petbot)"


class WebSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    tavily_api_key: str | None = None
    user_agent: str = DEFAULT_USER_AGENT

    @field_validator("tavily_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
