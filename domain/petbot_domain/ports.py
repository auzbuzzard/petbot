"""Ports: interfaces the domain defines and adapters implement (dependency inversion).

A *port* lets neutral logic drive a capability without importing the platform.
These are :class:`typing.Protocol` types — structural, so adapters satisfy them by
matching the shape, with no import back into the kernel.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from petbot_domain.context import DispatchRequest
    from petbot_domain.result import SkillResult

#: Invoked (with no arguments) when a track finishes on its own, so the caller can
#: advance a queue. Adapters schedule it on the event loop.
TrackFinishedCallback = Callable[[], Awaitable[None]]


@runtime_checkable
class VoicePort(Protocol):
    """Plays audio in the user's current voice conversation."""

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
class DispatchPort(Protocol):
    """Runs a skill on decoupled compute and returns its result.

    The implementation is a *frontend* adapter: it serialises the neutral request,
    invokes the worker (in-process, Lambda, or a queue), and maps the reply back to
    a ``SkillResult``. Long-running work may return a deferred-ack result and post
    the final output out-of-band via the same conversation.
    """

    async def dispatch(self, request: DispatchRequest) -> SkillResult:
        """Dispatch ``request`` to the worker that owns ``request.skill``."""
        ...
