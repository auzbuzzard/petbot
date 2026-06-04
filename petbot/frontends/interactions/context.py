"""Build a neutral :class:`SkillContext` from a Discord interaction payload.

The HTTP-Interactions counterpart to :mod:`petbot.frontends.discord.context`:
it maps the interaction JSON (a plain dict) onto the core's capability flags.
``supports_voice`` is always ``False`` here — voice needs a Gateway connection,
which a stateless endpoint cannot hold — so the registry hides ``/music``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from petbot.core.skills.context import Capabilities, Platform, SkillContext, User


def _raw_user(interaction: Mapping[str, Any]) -> Mapping[str, Any]:
    # Guild interactions nest the user under ``member``; DM interactions put it
    # at the top level under ``user``.
    member = interaction.get("member")
    if isinstance(member, Mapping):
        user = member.get("user")
        if isinstance(user, Mapping):
            return user
    user = interaction.get("user")
    return user if isinstance(user, Mapping) else {}


def _channel_is_nsfw(interaction: Mapping[str, Any]) -> bool:
    channel = interaction.get("channel")
    return bool(channel.get("nsfw", False)) if isinstance(channel, Mapping) else False


def build_context(interaction: Mapping[str, Any]) -> SkillContext:
    """Map an interaction payload onto a :class:`SkillContext`.

    ``allows_explicit`` follows the channel's NSFW flag; the conversation id keys
    off the channel (the natural session unit, matching the gateway adapter).
    """
    raw = _raw_user(interaction)
    user = User(
        platform=Platform.DISCORD,
        id=str(raw.get("id", "0")),
        display_name=str(raw.get("global_name") or raw.get("username") or "unknown"),
    )
    capabilities = Capabilities(
        allows_explicit=_channel_is_nsfw(interaction),
        supports_voice=False,
        supports_rich_embeds=True,
        max_text_length=2000,
    )
    return SkillContext(
        platform=Platform.DISCORD,
        user=user,
        conversation_id=f"discord:{interaction.get('channel_id')}",
        capabilities=capabilities,
    )
