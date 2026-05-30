"""Ports: interfaces the core defines and adapters implement (dependency inversion).

A *port* lets neutral logic drive a platform-specific capability without
importing the platform. The music skill, for example, owns the queue/skip-vote
logic and talks audio through :class:`VoicePort`; the Discord adapter provides
the concrete implementation backed by ``discord.py`` voice.

These are :class:`typing.Protocol` types — structural, so adapters satisfy them
just by matching the shape, with no import back into the core.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

#: Invoked (with no arguments) when a track finishes playing on its own, so the
#: caller can advance a queue. Adapters schedule it on the event loop.
TrackFinishedCallback = Callable[[], Awaitable[None]]


@runtime_checkable
class VoicePort(Protocol):
    """Plays audio in the user's current voice conversation.

    The skill supplies a resolvable source (e.g. a URL yt-dlp understands); the
    adapter handles extraction, transport, and playback.
    """

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
        own*. It is not invoked when playback is replaced or stopped explicitly.
        """
        ...

    async def stop(self) -> None:
        """Stop playback and disconnect."""
        ...

    def is_playing(self) -> bool:
        """Whether audio is currently playing."""
        ...
