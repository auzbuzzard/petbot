"""Ports: interfaces the domain defines and adapters implement (dependency inversion).

A *port* lets neutral logic drive a capability without importing the platform.
These are :class:`typing.Protocol` types — structural, so an adapter satisfies one
by matching the shape, with no import back into the kernel. Ports are **never**
serialised: they hold live connections (a voice socket), so the service that hosts
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
    async def join(self, channel_id: str) -> None: ...

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

    async def stop(self) -> None: ...

    def is_playing(self) -> bool: ...


@runtime_checkable
class VoiceProvider(Protocol):
    """Resolves the :class:`VoicePort` for a conversation.

    The music service (which holds its own gateway) implements this; the music
    skill calls it per request instead of reading a port off the context, keeping
    :class:`~petbot.domain.context.SkillContext` pure serialisable data. It takes
    the whole context because resolving a Discord voice channel needs the invoking
    user (from ``ctx.user``), not just the conversation.
    """

    def for_context(self, ctx: SkillContext) -> VoicePort | None: ...


@runtime_checkable
class StylePort(Protocol):
    """Rewrites a finished :class:`~petbot.domain.result.SkillResult`'s text into
    PetBot's voice — text style transfer: change the wording/register, preserve the
    meaning. It is the persona for a frontend that has no LLM of its own (a slash
    command); the ``@mention`` path needs none, since the chat agent already voices
    its output.
    """

    async def stylize(self, result: SkillResult, ctx: SkillContext) -> SkillResult: ...


@runtime_checkable
class Notifier(Protocol):
    async def deliver(self, conversation_id: str, result: SkillResult) -> None: ...
