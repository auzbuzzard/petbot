"""Ports: interfaces the domain defines and adapters implement (dependency inversion).

A *port* lets neutral logic drive a capability without importing the platform.
These are :class:`typing.Protocol` types — structural, so an adapter satisfies one
by matching the shape, with no import back into the kernel. Ports are **never**
serialised: they hold live connections (a voice socket), so the worker that hosts
a port-requiring skill resolves the port locally per ``conversation_id`` rather
than receiving it over the wire.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from petbot.domain.context import SkillContext
    from petbot.domain.result import SkillResult

#: Invoked (no arguments) when a track finishes on its own, so the caller can
#: advance a queue. Adapters schedule it on the event loop.
TrackFinishedCallback = Callable[[], Awaitable[None]]


@runtime_checkable
class VoicePort(Protocol):
    """Plays audio in one conversation's voice channel."""

    async def join(self, channel_id: str) -> None:
        """Connect to (or move to) the given voice channel."""
        ...

    async def play(
        self,
        source_url: str,
        *,
        volume: float = 0.6,
        on_finished: TrackFinishedCallback | None = None,
    ) -> None:
        """Begin playing ``source_url`` at ``volume`` (0.0-1.0).

        If ``on_finished`` is given, it is awaited once the track ends *on its
        own* — not when playback is replaced or stopped explicitly.
        """
        ...

    async def stop(self) -> None:
        """Stop playback and disconnect."""
        ...

    def is_playing(self) -> bool:
        """Whether audio is currently playing."""
        ...


@runtime_checkable
class VoiceProvider(Protocol):
    """Resolves the :class:`VoicePort` for a conversation.

    The music worker (which holds its own gateway) implements this; the music
    skill calls it per request instead of reading a port off the context, keeping
    :class:`~petbot.domain.context.SkillContext` pure serialisable data. It takes
    the whole context because resolving a Discord voice channel needs the invoking
    user (from ``ctx.user``), not just the conversation.
    """

    def for_context(self, ctx: SkillContext) -> VoicePort | None:
        """The voice port for this request, or ``None`` if voice is unavailable."""
        ...


@runtime_checkable
class StylePort(Protocol):
    """Rewrites a finished :class:`~petbot.domain.result.SkillResult`'s text into
    PetBot's voice — text style transfer: change the wording/register, preserve the
    meaning. It is the persona for a frontend that has no LLM of its own (a slash
    command); the ``@mention`` path needs none, since the chat agent already voices
    its output. An error result is returned unchanged.
    """

    async def stylize(self, result: SkillResult, ctx: SkillContext) -> SkillResult:
        """Return ``result`` with its text restyled in character (meaning intact)."""
        ...


@runtime_checkable
class StyleProvider(Protocol):
    """Resolves the :class:`StylePort` for a request, or ``None`` when no styling is
    wanted (the caller voices its own output). Like :class:`VoiceProvider` it is
    implemented worker-side and resolved per request, so the persona model never
    rides on the wire; the dispatch boundary applies the port it returns.
    """

    def for_context(self, ctx: SkillContext) -> StylePort | None:
        """The style port for this request, or ``None`` to leave the result as-is."""
        ...
