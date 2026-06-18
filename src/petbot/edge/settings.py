"""The edge's configuration: the gateway token and how to reach the worker.

The edge needs only ``DISCORD_TOKEN`` plus the worker address — never a skill
credential (those live with the worker). The transport is chosen by config so the
same edge runs against a local HTTP worker in dev and a Lambda worker in prod.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import field_validator, model_validator
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
    #: Worker HTTP endpoint — present iff ``transport == "http"`` (``WORKER_URL``).
    worker_url: str | None = None
    #: Worker Lambda function name — present iff ``transport == "lambda"`` (``WORKER_LAMBDA``).
    worker_lambda: str | None = None

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _require_transport_target(self) -> Self:
        # The chosen transport's target is required; fail fast at construction
        # rather than scattering None-checks at the call site.
        if self.transport == "http" and not self.worker_url:
            raise ValueError("transport=http requires WORKER_URL.")
        if self.transport == "lambda" and not self.worker_lambda:
            raise ValueError("transport=lambda requires WORKER_LAMBDA.")
        return self
