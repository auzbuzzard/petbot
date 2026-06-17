"""The capability vocabulary shared by skills (requirements) and frontends (provisions).

A :class:`Capability` is a *hard* requirement/provision: a skill that lists one in
:attr:`~petbot_domain.skill.Skill.requires` is hidden on a frontend that does not
provide it. Soft, per-request facts (e.g. whether *this* channel allows explicit
content) are **not** capabilities — they live on
:class:`~petbot_domain.context.SkillContext` as runtime flags the skill reads.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    """A capability a frontend can *provide* and a skill can *require*."""

    #: A voice transport is available (the frontend can supply a ``VoicePort``).
    VOICE = "voice"
    #: The frontend delivers message content (Discord's privileged intent) — the
    #: conversational/LLM entrypoint needs this; slash commands do not.
    MESSAGE_CONTENT = "message_content"
    #: The frontend can render rich cards (``EmbedSpec``).
    RICH_EMBEDS = "rich_embeds"
