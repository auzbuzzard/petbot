"""The Discord frontend's configuration: the gateway token and the compute service.

The service target is a **discriminated union** (``SERVICE__KIND`` selects the variant),
so only the fields that apply to the chosen transport exist — no ``str | None`` bag where
half the values are inapplicable. Set via nested env vars, e.g. ``SERVICE__KIND=http`` +
``SERVICE__URL=…`` or ``SERVICE__KIND=lambda`` + ``SERVICE__FUNCTION_NAME=…``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HttpService(BaseModel):
    """Reach the compute service over HTTP."""

    kind: Literal["http"] = "http"
    url: str


class LambdaService(BaseModel):
    """Reach the compute service by invoking a Lambda."""

    kind: Literal["lambda"] = "lambda"
    function_name: str


#: Exactly one transport, with only its own fields. Tagged by ``kind``.
ServiceTarget = Annotated[HttpService | LambdaService, Field(discriminator="kind")]


class DiscordSettings(BaseSettings):
    """Configuration for the always-on Discord frontend."""

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
    #: The compute service to dispatch to (required; see ``SERVICE__*``).
    service: ServiceTarget

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
