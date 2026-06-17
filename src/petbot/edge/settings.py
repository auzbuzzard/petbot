"""The edge's configuration: the gateway token and how to reach the worker.

The edge needs only ``DISCORD_TOKEN`` plus the worker address — never a skill
credential (those live with the worker). The transport is chosen by config so the
same edge runs against a local HTTP worker in dev and a Lambda worker in prod.
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TransportKind = Literal["http", "lambda"]


class EdgeSettings(BaseSettings):
    """Configuration for the always-on Discord edge."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    discord_token: str
    dev_guild_id: int | None = None
    log_level: str = "INFO"

    transport: TransportKind = "http"
    #: Worker HTTP endpoint (used when ``transport == "http"``).
    worker_url: str = "http://localhost:8000/dispatch"
    #: Worker Lambda function name (used when ``transport == "lambda"``).
    worker_lambda: str | None = None

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
