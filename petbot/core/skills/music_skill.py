"""The music skill: neutral queue + skip-vote logic over a :class:`VoicePort`.

The queue and skip-vote bookkeeping (ported from the legacy per-guild
``VoiceState``) live here, in the platform-neutral core; the actual audio
transport is delegated to the :class:`~petbot.core.skills.ports.VoicePort` the
adapter injects via ``ctx.voice``. The skill therefore declares
``requires={"voice"}`` and is only offered on frontends that supply that port.

Known limitation: :class:`VoicePort` has no "track finished" callback, so the
queue advances on an explicit ``skip``/``stop`` rather than automatically. This
is documented in ``docs/architecture.md`` as a deliberate, additive follow-up.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from petbot.core.skills.base import Skill
from petbot.core.skills.context import SkillContext, SkillResult

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


class MusicSkill(Skill):
    """Play and manage audio in a voice conversation."""

    name: ClassVar[str] = "music"
    description: ClassVar[str] = "Play audio in a voice channel: play, skip, stop, queue, volume."
    requires: ClassVar[frozenset[str]] = frozenset({"voice"})
    input_schema: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play", "skip", "stop", "queue", "volume"],
                "description": "What to do.",
            },
            "query": {
                "type": "string",
                "description": "For 'play': a URL or search the audio source supports.",
            },
            "level": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "For 'volume': the volume percentage (0-100).",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self._states: dict[str, ConversationMusic] = {}

    def _state(self, conversation_id: str) -> ConversationMusic:
        state = self._states.get(conversation_id)
        if state is None:
            state = ConversationMusic()
            self._states[conversation_id] = state
        return state

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        if ctx.voice is None:
            return SkillResult.failure("I'm not able to use voice here.")

        action = str(args.get("action", "")).lower()
        state = self._state(ctx.conversation_id)

        if action == "play":
            return await self._play(args, ctx, state)
        if action == "skip":
            return await self._skip(ctx, state)
        if action == "stop":
            return await self._stop(ctx, state)
        if action == "queue":
            return self._show_queue(state)
        if action == "volume":
            return self._set_volume(args, state)
        return SkillResult.failure(f"Unknown music action: {action!r}.")

    async def _play(
        self, args: Mapping[str, Any], ctx: SkillContext, state: ConversationMusic
    ) -> SkillResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return SkillResult.failure("Tell me what to play (a URL or search terms).")
        assert ctx.voice is not None
        track = Track(
            source_url=query,
            requested_by_id=ctx.user.id,
            requested_by_name=ctx.user.display_name,
        )
        if state.current is not None and ctx.voice.is_playing():
            state.queue.append(track)
            return SkillResult.message(f"Enqueued **{query}** (position {len(state.queue)}).")

        state.current = track
        state.skip_votes.clear()
        await ctx.voice.play(track.source_url, volume=state.volume)
        return SkillResult.message(f"▶️ Now playing **{query}**.")

    async def _skip(self, ctx: SkillContext, state: ConversationMusic) -> SkillResult:
        if state.current is None:
            return SkillResult.message("Not playing anything right now.")
        assert ctx.voice is not None

        is_requester = ctx.user.id == state.current.requested_by_id
        if not is_requester:
            if ctx.user.id in state.skip_votes:
                return SkillResult.message("You've already voted to skip.")
            state.skip_votes.add(ctx.user.id)
            if len(state.skip_votes) < SKIP_THRESHOLD:
                votes = len(state.skip_votes)
                return SkillResult.message(f"Skip vote added [{votes}/{SKIP_THRESHOLD}].")

        return await self._advance(ctx, state)

    async def _advance(self, ctx: SkillContext, state: ConversationMusic) -> SkillResult:
        assert ctx.voice is not None
        state.skip_votes.clear()
        if state.queue:
            state.current = state.queue.popleft()
            await ctx.voice.play(state.current.source_url, volume=state.volume)
            return SkillResult.message(f"⏭️ Skipped. Now playing **{state.current.source_url}**.")
        state.current = None
        await ctx.voice.stop()
        return SkillResult.message("⏭️ Skipped. Nothing left in the queue.")

    async def _stop(self, ctx: SkillContext, state: ConversationMusic) -> SkillResult:
        assert ctx.voice is not None
        state.queue.clear()
        state.current = None
        state.skip_votes.clear()
        await ctx.voice.stop()
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

    def _set_volume(self, args: Mapping[str, Any], state: ConversationMusic) -> SkillResult:
        level = args.get("level")
        if level is None:
            return SkillResult.failure("Give me a volume level between 0 and 100.")
        state.volume = max(0, min(100, int(level))) / 100
        return SkillResult.message(
            f"🔊 Volume set to {state.volume:.0%} (applies to the next track)."
        )
