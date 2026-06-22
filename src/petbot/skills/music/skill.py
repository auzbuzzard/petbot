"""The music skill: neutral queue + skip-vote logic over a :class:`VoicePort`.

The queue and skip-vote bookkeeping live here, in the platform-neutral core; the
actual audio transport is delegated to a :class:`VoicePort`. Because a live voice
port can't cross the wire, the skill resolves it per request from an injected
:class:`VoiceProvider` keyed by ``conversation_id`` (the music service, which holds
its own gateway, supplies the provider) — rather than reading it off the context.
The skill therefore declares ``requires={Capability.VOICE}`` and is only hosted by
a service that can provide voice.

The queue **auto-advances**: each track starts with an ``on_finished`` callback
that plays the next queued track when the current one ends on its own. A
per-conversation ``play_token`` guards against stale callbacks — an explicit
``skip``/``stop`` bumps the token, so the finished-callback fired by tearing down
the old track is recognised as superseded and ignored (no double-advance).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from petbot.domain import (
    Capability,
    InvalidInput,
    Skill,
    SkillContext,
    SkillError,
    SkillResult,
    TrackFinishedCallback,
    VoicePort,
    VoiceProvider,
)
from petbot.types import MusicArgs

logger = logging.getLogger(__name__)

#: Skip votes required (besides the requester, who may always self-skip).
SKIP_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class Track:
    """A queued audio source."""

    source_url: str
    requested_by_id: str
    requested_by_name: str


@dataclass
class ConversationMusic:
    """Per-conversation playback state (queue, current track, votes, volume)."""

    queue: deque[Track] = field(default_factory=deque)
    current: Track | None = None
    skip_votes: set[str] = field(default_factory=set)
    volume: float = 0.6
    # Bumped whenever playback changes by an explicit action; lets a finished
    # callback detect that it has been superseded.
    play_token: int = 0


class MusicSkill(Skill[MusicArgs]):
    """Play and manage audio in a voice conversation."""

    name = "music"
    description = "Play audio in a voice channel: play, skip, stop, queue, volume."
    args_model = MusicArgs
    requires = frozenset({Capability.VOICE})

    def __init__(self, voice: VoiceProvider) -> None:
        self._voice = voice
        self._states: dict[str, ConversationMusic] = {}

    def _state(self, conversation_id: str) -> ConversationMusic:
        state = self._states.get(conversation_id)
        if state is None:
            state = ConversationMusic()
            self._states[conversation_id] = state
        return state

    async def run(self, args: MusicArgs, ctx: SkillContext) -> SkillResult:
        voice = self._voice.for_context(ctx)
        if voice is None:
            raise SkillError("I'm not able to use voice here.")

        state = self._state(ctx.conversation_id)
        if args.action == "play":
            return await self._play(args, ctx, voice, state)
        if args.action == "skip":
            return await self._skip(ctx, voice, state)
        if args.action == "stop":
            return await self._stop(voice, state)
        if args.action == "queue":
            return self._show_queue(state)
        if args.action == "volume":
            return self._set_volume(args, state)
        raise SkillError(f"Unknown music action: {args.action!r}.")

    async def _start(self, state: ConversationMusic, voice: VoicePort, track: Track) -> None:
        """Make ``track`` the current track and begin playing it."""
        state.current = track
        state.skip_votes.clear()
        state.play_token += 1
        token = state.play_token
        logger.info(
            "music: now playing %r (requested by %s)", track.source_url, track.requested_by_name
        )
        await voice.play(
            track.source_url,
            volume=state.volume,
            on_finished=self._on_finished(state, voice, token),
        )

    def _on_finished(
        self, state: ConversationMusic, voice: VoicePort, token: int
    ) -> TrackFinishedCallback:
        """Build the callback that advances the queue when a track ends naturally."""

        async def _advance_on_end() -> None:
            if token != state.play_token:
                return  # superseded by an explicit skip/stop or a newer track
            if state.queue:
                await self._start(state, voice, state.queue.popleft())
            else:
                state.current = None
                state.play_token += 1

        return _advance_on_end

    async def _play(
        self, args: MusicArgs, ctx: SkillContext, voice: VoicePort, state: ConversationMusic
    ) -> SkillResult:
        query = (args.query or "").strip()
        if not query:
            raise InvalidInput("Tell me what to play (a URL or search terms).")
        track = Track(
            source_url=query,
            requested_by_id=ctx.user.id,
            requested_by_name=ctx.user.display_name,
        )
        if state.current is not None and voice.is_playing():
            state.queue.append(track)
            logger.debug("music: enqueued %r at position %d", query, len(state.queue))
            return SkillResult.message(f"Enqueued **{query}** (position {len(state.queue)}).")

        await self._start(state, voice, track)
        return SkillResult.message(f"▶️ Now playing **{query}**.")

    async def _skip(
        self, ctx: SkillContext, voice: VoicePort, state: ConversationMusic
    ) -> SkillResult:
        if state.current is None:
            return SkillResult.message("Not playing anything right now.")

        is_requester = ctx.user.id == state.current.requested_by_id
        if not is_requester:
            if ctx.user.id in state.skip_votes:
                return SkillResult.message("You've already voted to skip.")
            state.skip_votes.add(ctx.user.id)
            if len(state.skip_votes) < SKIP_THRESHOLD:
                votes = len(state.skip_votes)
                return SkillResult.message(f"Skip vote added [{votes}/{SKIP_THRESHOLD}].")

        return await self._advance(state, voice)

    async def _advance(self, state: ConversationMusic, voice: VoicePort) -> SkillResult:
        if state.queue:
            next_track = state.queue.popleft()
            # _start bumps play_token, so the finished-callback fired by tearing
            # down the current track is recognised as stale and ignored.
            await self._start(state, voice, next_track)
            return SkillResult.message(f"⏭️ Skipped. Now playing **{next_track.source_url}**.")
        state.current = None
        state.skip_votes.clear()
        state.play_token += 1  # invalidate the pending finished-callback
        await voice.stop()
        return SkillResult.message("⏭️ Skipped. Nothing left in the queue.")

    async def _stop(self, voice: VoicePort, state: ConversationMusic) -> SkillResult:
        state.queue.clear()
        state.current = None
        state.skip_votes.clear()
        state.play_token += 1  # invalidate the pending finished-callback
        await voice.stop()
        logger.debug("music: stopped playback and cleared the queue")
        return SkillResult.message("⏹️ Stopped and cleared the queue.")

    def _show_queue(self, state: ConversationMusic) -> SkillResult:
        if state.current is None and not state.queue:
            return SkillResult.message("The queue is empty.")
        lines: list[str] = []
        if state.current is not None:
            lines.append(f"**Now playing:** {state.current.source_url}")
        for index, track in enumerate(state.queue, start=1):
            lines.append(f"{index}. {track.source_url} (by {track.requested_by_name})")
        return SkillResult.message("\n".join(lines))

    def _set_volume(self, args: MusicArgs, state: ConversationMusic) -> SkillResult:
        if args.level is None:
            raise InvalidInput("Give me a volume level between 0 and 100.")
        state.volume = max(0, min(100, args.level)) / 100
        return SkillResult.message(
            f"🔊 Volume set to {state.volume:.0%} (applies to the next track)."
        )
