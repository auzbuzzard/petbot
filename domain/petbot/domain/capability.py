"""The capability vocabulary shared by skills (requirements) and frontends (provisions).

A :class:`Capability` is a *hard* requirement/provision: a skill that lists one
in :attr:`~petbot.domain.skill.Skill.requires` is only hosted by a worker that can
provide it (music needs a voice transport). Soft, per-request facts — whether
*this* channel allows explicit content — are **not** capabilities; they live on
:class:`~petbot.domain.context.SkillContext` as runtime flags the skill reads.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    """A capability a worker can *provide* and a skill can *require*."""

    #: A voice transport is available (the worker can supply a ``VoicePort``).
    VOICE = "voice"
    #: The frontend delivers message content (Discord's privileged intent) — the
    #: conversational/LLM entrypoint needs this; slash commands do not.
    MESSAGE_CONTENT = "message_content"
    #: The frontend can render rich cards (``EmbedSpec``).
    RICH_EMBEDS = "rich_embeds"
