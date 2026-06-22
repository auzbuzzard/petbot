"""The booru skills' own configuration (the credentials they need).

A skill package reads exactly the environment it needs, so it stays
self-contained — no shared config import couples a skill to the platform. The
compute service supplies these via the environment (``op run``, a ``.env``, or
injected container/Lambda vars); missing optional creds simply mean
unauthenticated, lower-rate-limit requests.
"""

from __future__ import annotations

from importlib.metadata import version

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Descriptive User-Agent sent to booru APIs (a spoofed one gets blocked). The
#: version is read from the installed package metadata, never hard-coded.
DEFAULT_USER_AGENT = f"PetBot/{version('petbot')} (https://github.com/auzbuzzard/petbot)"


class BooruSettings(BaseSettings):
    """Credentials and identification for the booru providers."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    e621_username: str | None = None
    e621_api_key: str | None = None
    derpibooru_api_key: str | None = None
    user_agent: str = DEFAULT_USER_AGENT

    @field_validator("e621_username", "e621_api_key", "derpibooru_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
