"""The music worker's configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class MusicSettings(BaseSettings):
    """Gateway token and the dispatch endpoint the edge calls."""

    model_config = SettingsConfigDict(
        env_prefix="music_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    discord_token: str
    dispatch_host: str = "0.0.0.0"
    dispatch_port: int = 8100
    log_level: str = "INFO"
