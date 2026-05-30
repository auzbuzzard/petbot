"""Neutral value objects exchanged across the core <-> adapter boundary.

Everything here is a frozen, slotted dataclass: hashable, cheap, and immune to
accidental mutation. None of it mentions Discord — adapters map their native
objects onto these types on the way in, and render these types on the way out.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from petbot.core.skills.ports import VoicePort


class Platform(StrEnum):
    """The frontend a request originated from.

    Only Discord exists today; ``TELEGRAM``, ``WEB``, etc. are added by future
    adapters. Skills must never branch on this — they branch on
    :class:`Capabilities` instead.
    """

    DISCORD = "discord"


@dataclass(frozen=True, slots=True)
class User:
    """The invoking user, platform-qualified.

    ``id`` is kept as ``str`` for neutrality (Discord snowflakes, Telegram ints,
    and web UUIDs all coexist).
    """

    platform: Platform
    id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What the originating frontend/conversation supports.

    Skills inspect these flags instead of asking "which platform am I on?". The
    Discord adapter, for example, fills ``allows_explicit`` from
    ``channel.is_nsfw()`` and ``supports_voice`` from whether it can supply a
    :class:`~petbot.core.skills.ports.VoicePort`.
    """

    allows_explicit: bool = False
    supports_voice: bool = False
    supports_rich_embeds: bool = True
    max_text_length: int = 2000


@dataclass(frozen=True, slots=True)
class SkillContext:
    """Everything a skill needs about the request, with no platform nouns."""

    platform: Platform
    user: User
    conversation_id: str  # neutral key for sessions (Phase B LLM layer)
    capabilities: Capabilities
    # Present iff ``capabilities.supports_voice``; the adapter injects a concrete
    # implementation backed by its own voice stack.
    voice: VoicePort | None = None


@dataclass(frozen=True, slots=True)
class EmbedSpec:
    """A platform-neutral description of a rich card.

    Adapters translate this into their native rich-message type (Discord turns
    it into a ``discord.Embed``). It is never a ``discord.Embed`` itself.
    """

    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    image_url: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    author_icon_url: str | None = None


@dataclass(frozen=True, slots=True)
class SkillResult:
    """The neutral outcome of running a skill.

    Carries optional ``text``, an optional :class:`EmbedSpec`, attached file
    paths/URLs, and an optional ``error`` string for *expected* failures
    (empty search, bad input). Rendering and length-chunking are the adapter's
    job, never the skill's.
    """

    text: str | None = None
    embed: EmbedSpec | None = None
    files: tuple[str, ...] = ()
    error: str | None = None

    @property
    def is_error(self) -> bool:
        """Whether this result represents an expected failure."""
        return self.error is not None

    @classmethod
    def message(
        cls,
        text: str | None = None,
        *,
        embed: EmbedSpec | None = None,
        files: tuple[str, ...] = (),
    ) -> SkillResult:
        """Build a successful result."""
        return cls(text=text, embed=embed, files=files)

    @classmethod
    def failure(cls, error: str) -> SkillResult:
        """Build an expected-failure result (rendered as a friendly message)."""
        return cls(error=error)


__all__ = [
    "Capabilities",
    "EmbedSpec",
    "Platform",
    "SkillContext",
    "SkillResult",
    "User",
]
