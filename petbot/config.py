"""Runtime configuration.

The whole application reads configuration from the process environment. It does
**not** care how the environment was populated — ``op run`` (1Password), a
plaintext ``.env``, real exported shell variables, or a container/Lambda's
injected env all work identically. That keeps secret management an operational
choice with zero code lock-in.

Configuration is modelled with :mod:`pydantic_settings`: a shared
:class:`AppSettings` base holds what *every* frontend needs, and one subclass per
frontend (:class:`GatewaySettings`, :class:`InteractionsSettings`) declares the
secrets *that* frontend requires. So each entrypoint validates exactly its own
inputs and fails fast with a :class:`pydantic.ValidationError` when something is
missing — the gateway needs ``DISCORD_TOKEN``; the Lambda needs only
``DISCORD_PUBLIC_KEY`` and never the bot token. ``.env`` loading is built in, so
there is no separate dotenv call at the entrypoints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Default User-Agent sent to booru APIs (overridable via ``USER_AGENT``). The
#: legacy spoofed-Firefox UA gets blocked; a descriptive one is now required.
DEFAULT_USER_AGENT = "PetBot/2.0 (https://github.com/auzbuzzard/petbot)"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed.

    The entrypoints use this to translate a :class:`pydantic.ValidationError`
    into a short, operator-friendly message (e.g. "copy ``.env.example``…").
    """


class AppSettings(BaseSettings):
    """Configuration shared by every frontend.

    Read from the process environment (and a local ``.env`` if present), so it is
    agnostic to how the env was populated. Frozen, like the rest of the app's
    config: built once at start-up and injected downward.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    env: str = "dev"
    e621_username: str | None = None
    e621_api_key: str | None = None
    derpibooru_api_key: str | None = None
    user_agent: str = DEFAULT_USER_AGENT
    log_level: str = "INFO"
    #: ``"plain"`` | ``"json"``, or ``None`` to derive from :attr:`env`.
    log_format: Literal["plain", "json"] | None = None

    @field_validator("e621_username", "e621_api_key", "derpibooru_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        # Treat an explicitly-empty env var (``E621_API_KEY=``) as unset, matching
        # the previous ``env.get(...) or None`` behaviour.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_format", mode="before")
    @classmethod
    def _normalise_log_format(cls, value: object) -> object:
        # Accept any case (``Plain``) and treat a blank value as unset.
        if isinstance(value, str):
            return value.strip().lower() or None
        return value

    @property
    def is_prod(self) -> bool:
        """Whether the bot is running against the production environment."""
        return self.env.lower() == "prod"

    @property
    def resolved_log_format(self) -> str:
        """The logging profile to use: an explicit ``LOG_FORMAT`` wins, else it is
        derived from :attr:`env` (``prod`` → structured JSON, otherwise plain)."""
        if self.log_format is not None:
            return self.log_format
        return "json" if self.is_prod else "plain"


class GatewaySettings(AppSettings):
    """Configuration for the Discord **gateway** frontend.

    The gateway is the parked ``/music`` worker (the blessed deploy path is the
    serverless Lambda; see ADR 0005). It requires ``DISCORD_TOKEN`` for the
    WebSocket login; the public key is not used on this path.
    """

    discord_token: str
    dev_guild_id: int | None = None

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _blank_guild_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class InteractionsSettings(AppSettings):
    """Configuration for the **HTTP-Interactions** frontend (AWS Lambda).

    Requires ``DISCORD_PUBLIC_KEY`` to verify Discord's Ed25519 request
    signatures. The bot token is never used at request time, so it is **not**
    required here — the Lambda boots on the public key alone.
    """

    discord_public_key: str
