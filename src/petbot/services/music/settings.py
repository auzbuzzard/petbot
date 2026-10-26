from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class MusicSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="music_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    discord_token: str
    #: Bind address for the dispatch endpoint (required) — set via
    #: ``MUSIC_DISPATCH_HOST`` (e.g. ``0.0.0.0`` to accept the frontend across the
    #: network). Never defaulted, so the bind is always an explicit choice.
    dispatch_host: str
    dispatch_port: int
    log_level: str = "INFO"
