"""Register the interactions app's slash commands with Discord.

Run from CI (never a developer machine); see ``.github/workflows/deploy.yml``.
Because Discord stores commands per *application*, registration is a single
**bulk-overwrite PUT** of :data:`~petbot.frontends.interactions.commands.COMMANDS`
— idempotent and declarative: the PUT replaces whatever was there, so re-running
it on every deploy only changes Discord when the command set changes.

Scope:

* ``DISCORD_GUILD_ID`` set  -> guild-scoped registration. Appears **instantly**
  in just that guild — the dev-guild rollout path.
* ``DISCORD_GUILD_ID`` unset -> global registration. App-wide, but Discord may
  take up to ~1 hour to propagate it everywhere.

Auth uses the bot token (``Authorization: Bot ...``). The Lambda never needs the
token at request time (it verifies only the Ed25519 signature), so it lives in
SSM and is exported into this process by CI — it is never written to disk.

Run::

    python -m petbot.frontends.interactions.register

Required env: ``DISCORD_APP_ID``, ``DISCORD_BOT_TOKEN``.
Optional env: ``DISCORD_GUILD_ID`` (guild-scoped when present), ``LOG_LEVEL``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from petbot.frontends.interactions.commands import COMMANDS
from petbot.logging_setup import configure_logging

logger = logging.getLogger(__name__)

#: Discord REST API base. v10 is the current stable application-commands API.
API_BASE = "https://discord.com/api/v10"

#: How long to wait on the single PUT before giving up.
_TIMEOUT_SECONDS = 30.0


class RegisterError(RuntimeError):
    """Raised when registration cannot run or Discord rejects the request."""


def _endpoint(app_id: str, guild_id: str | None) -> str:
    """The bulk-overwrite URL: guild-scoped when ``guild_id`` is given, else global."""
    if guild_id:
        return f"{API_BASE}/applications/{app_id}/guilds/{guild_id}/commands"
    return f"{API_BASE}/applications/{app_id}/commands"


def register(app_id: str, bot_token: str, guild_id: str | None = None) -> list[dict[str, Any]]:
    """PUT the full command set to Discord and return the registered commands.

    Raises :class:`RegisterError` on any non-2xx response. The bot token is sent
    only in the ``Authorization`` header and is never logged.
    """
    response = httpx.put(
        _endpoint(app_id, guild_id),
        headers={"Authorization": f"Bot {bot_token}"},
        json=COMMANDS,
        timeout=_TIMEOUT_SECONDS,
    )
    if response.is_error:
        # response.text is Discord's error JSON — it never echoes the token.
        raise RegisterError(
            f"Discord rejected command registration ({response.status_code}): {response.text}"
        )
    registered: list[dict[str, Any]] = response.json()
    return registered


def main() -> None:
    """Entry point: read config from the environment and register the commands."""
    configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"), fmt="plain")

    app_id = os.environ.get("DISCORD_APP_ID", "").strip()
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip() or None
    if not app_id or not bot_token:
        raise RegisterError("DISCORD_APP_ID and DISCORD_BOT_TOKEN are both required.")

    scope = f"guild {guild_id}" if guild_id else "global"
    registered = register(app_id, bot_token, guild_id)
    logger.info(
        "Registered %d command(s) (%s): %s",
        len(registered),
        scope,
        ", ".join(command["name"] for command in COMMANDS),
    )


if __name__ == "__main__":
    main()
