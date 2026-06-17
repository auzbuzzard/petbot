"""The music skill's neutral queue + skip-vote logic, over a fake VoicePort."""

from __future__ import annotations

from petbot.domain import Platform, SkillContext, TrackFinishedCallback, User, VoicePort
from petbot.skills.music import MusicSkill
from petbot.skills.music.skill import SKIP_THRESHOLD
from petbot.types import MusicArgs


class FakeVoicePort:
    """Records playback calls; ``on_finished`` is captured, never auto-fired."""

    def __init__(self) -> None:
        self.played: list[str] = []
        self.stopped = False
        self._playing = False
        self.last_on_finished: TrackFinishedCallback | None = None

    async def join(self, channel_id: str) -> None:  # pragma: no cover - unused
        ...

    async def play(
        self,
        source_url: str,
        *,
        volume: float = 0.6,
        on_finished: TrackFinishedCallback | None = None,
    ) -> None:
        self.played.append(source_url)
        self._playing = True
        self.last_on_finished = on_finished

    async def stop(self) -> None:
        self.stopped = True
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing


class FakeVoiceProvider:
    def __init__(self, port: VoicePort | None) -> None:
        self._port = port

    def for_context(self, ctx: SkillContext) -> VoicePort | None:
        return self._port


def _ctx(user_id: str = "u1", display_name: str = "Rex") -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id=user_id, display_name=display_name),
        conversation_id="conv-1",
    )


async def test_play_then_enqueue_then_autoadvance() -> None:
    port = FakeVoicePort()
    skill = MusicSkill(FakeVoiceProvider(port))

    first = await skill.run(MusicArgs(action="play", query="song-a"), _ctx())
    assert "Now playing" in (first.text or "")
    assert port.played == ["song-a"]

    second = await skill.run(MusicArgs(action="play", query="song-b"), _ctx())
    assert "Enqueued" in (second.text or "")

    # The current track ends on its own -> the queued track auto-advances.
    assert port.last_on_finished is not None
    await port.last_on_finished()
    assert port.played == ["song-a", "song-b"]


async def test_requester_self_skip_advances_immediately() -> None:
    port = FakeVoicePort()
    skill = MusicSkill(FakeVoiceProvider(port))
    await skill.run(MusicArgs(action="play", query="song-a"), _ctx(user_id="u1"))
    await skill.run(MusicArgs(action="play", query="song-b"), _ctx(user_id="u1"))

    result = await skill.run(MusicArgs(action="skip"), _ctx(user_id="u1"))
    assert "Skipped" in (result.text or "")
    assert port.played == ["song-a", "song-b"]


async def test_skip_needs_votes_from_non_requesters() -> None:
    port = FakeVoicePort()
    skill = MusicSkill(FakeVoiceProvider(port))
    await skill.run(MusicArgs(action="play", query="song-a"), _ctx(user_id="owner"))

    for i in range(SKIP_THRESHOLD - 1):
        out = await skill.run(MusicArgs(action="skip"), _ctx(user_id=f"voter-{i}"))
        assert "Skip vote added" in (out.text or "")
    final = await skill.run(MusicArgs(action="skip"), _ctx(user_id="voter-last"))
    assert "Skipped" in (final.text or "")


async def test_stop_clears_and_disconnects() -> None:
    port = FakeVoicePort()
    skill = MusicSkill(FakeVoiceProvider(port))
    await skill.run(MusicArgs(action="play", query="song-a"), _ctx())
    out = await skill.run(MusicArgs(action="stop"), _ctx())
    assert "Stopped" in (out.text or "")
    assert port.stopped


async def test_volume_clamps_and_persists() -> None:
    skill = MusicSkill(FakeVoiceProvider(FakeVoicePort()))
    out = await skill.run(MusicArgs(action="volume", level=150), _ctx())
    assert "100%" in (out.text or "")


async def test_voice_unavailable_is_friendly_failure() -> None:
    skill = MusicSkill(FakeVoiceProvider(None))
    out = await skill.run(MusicArgs(action="play", query="x"), _ctx())
    assert out.is_error
