"""Runtime configuration.

The whole application reads configuration from a process environment through the
:class:`Settings` value object. It does **not** care how the environment was
populated — ``op run`` (1Password), a plaintext ``.env``, real exported shell
variables, or a container orchestrator all work identically. That keeps secret
management an operational choice with zero code lock-in.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

#: Default User-Agent sent to booru APIs (overridable via ``USER_AGENT``). The
#: legacy spoofed-Firefox UA gets blocked; a descriptive one is now required.
DEFAULT_USER_AGENT = "PetBot/2.0 (https://github.com/auzbuzzard/petbot)"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved runtime settings.

    Built once at start-up via :meth:`from_env` and injected downwards; nothing
    reads ``os.environ`` directly except :meth:`from_env`.
    """

    discord_token: str
    env: str = "dev"
    dev_guild_id: int | None = None
    e621_username: str | None = None
    e621_api_key: str | None = None
    derpibooru_api_key: str | None = None
    user_agent: str = DEFAULT_USER_AGENT
    log_level: str = "INFO"
    #: ``"plain"`` | ``"json"``, or ``None`` to derive from :attr:`env`.
    log_format: str | None = None

    @property
    def is_prod(self) -> bool:
        """Whether the bot is running against the production environment."""
        return self.env.lower() == "prod"

    @property
    def resolved_log_format(self) -> str:
        """The logging profile to use: explicit ``LOG_FORMAT`` wins, else derived
        from the environment (``prod`` → structured JSON, otherwise human-readable)."""
        if self.log_format is not None:
            return self.log_format
        return "json" if self.is_prod else "plain"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build :class:`Settings` from a mapping (defaults to ``os.environ``).

        Raises :class:`ConfigError` if ``DISCORD_TOKEN`` is absent or if
        ``DEV_GUILD_ID`` is set but not an integer.
        """
        env = os.environ if environ is None else environ

        token = env.get("DISCORD_TOKEN")
        if not token:
            raise ConfigError(
                "DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in, "
                "then launch with `op run --env-file=.env -- python -m petbot` "
                "(or export the variables yourself)."
            )

        raw_guild = env.get("DEV_GUILD_ID")
        if raw_guild:
            try:
                dev_guild_id: int | None = int(raw_guild)
            except ValueError as exc:
                raise ConfigError(f"DEV_GUILD_ID must be an integer, got {raw_guild!r}.") from exc
        else:
            dev_guild_id = None

        log_format = env.get("LOG_FORMAT") or None
        if log_format is not None:
            log_format = log_format.lower()
            if log_format not in ("plain", "json"):
                raise ConfigError(
                    f"LOG_FORMAT must be 'plain' or 'json', got {env['LOG_FORMAT']!r}."
                )

        return cls(
            discord_token=token,
            env=env.get("ENV", "dev"),
            dev_guild_id=dev_guild_id,
            e621_username=env.get("E621_USERNAME") or None,
            e621_api_key=env.get("E621_API_KEY") or None,
            derpibooru_api_key=env.get("DERPIBOORU_API_KEY") or None,
            user_agent=env.get("USER_AGENT") or DEFAULT_USER_AGENT,
            log_level=env.get("LOG_LEVEL") or "INFO",
            log_format=log_format,
        )
