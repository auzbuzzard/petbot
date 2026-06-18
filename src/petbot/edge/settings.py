"""The edge's configuration: the gateway token and how to reach the worker.

The worker target is a **discriminated union** (``WORKER__KIND`` selects the
variant), so only the fields that apply to the chosen transport exist — no
``str | None`` bag where half the values are inapplicable. Set via nested env
vars, e.g. ``WORKER__KIND=http`` + ``WORKER__URL=…`` or ``WORKER__KIND=lambda`` +
``WORKER__FUNCTION_NAME=…``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HttpWorker(BaseModel):
    """Reach the worker over HTTP."""

    kind: Literal["http"] = "http"
    url: str


class LambdaWorker(BaseModel):
    """Reach the worker by invoking a Lambda."""

    kind: Literal["lambda"] = "lambda"
    function_name: str


#: Exactly one transport, with only its own fields. Tagged by ``kind``.
WorkerTarget = Annotated[HttpWorker | LambdaWorker, Field(discriminator="kind")]


class EdgeSettings(BaseSettings):
    """Configuration for the always-on Discord edge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    discord_token: str
    dev_guild_id: int | None = None
    log_level: str = "INFO"
    #: The worker to dispatch to (required; see ``WORKER__*``).
    worker: WorkerTarget

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
