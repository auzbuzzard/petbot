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

from petbot.frontends.discord.thinking import THINKING_AFTER_SECONDS


class HttpService(BaseModel):
    kind: Literal["http"] = "http"
    url: str


class LambdaService(BaseModel):
    kind: Literal["lambda"] = "lambda"
    function_name: str


ServiceTarget = Annotated[HttpService | LambdaService, Field(discriminator="kind")]


class DiscordSettings(BaseSettings):
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
    #: How many reply-chain ancestors to fetch when reconstructing conversation history
    #: (a Discord-API cost bound, not a model-context bound). Env ``HISTORY_MAX_TURNS``.
    history_max_turns: int = 25
    #: Seconds into a conversational turn at which the typing indicator pauses once, as a
    #: person's would, before it resumes. Env ``THINKING_AFTER_SECONDS``.
    thinking_after_seconds: float = Field(default=THINKING_AFTER_SECONDS, gt=0)
    service: ServiceTarget
    #: DynamoDB table of claimed message ids (``CLAIMS_TABLE``), so that of every copy of
    #: the frontend on the gateway exactly one handles each message. Unset ⇒ no claiming.
    claims_table: str | None = None

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
