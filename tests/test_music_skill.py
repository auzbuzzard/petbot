"""Tests for the neutral music skill, driven through a fake VoicePort."""

from __future__ import annotations

from conftest import make_context

from petbot.core.skills.music_skill import SKIP_THRESHOLD, MusicSkill
from petbot.core.skills.ports import TrackFinishedCallback


class FakeVoicePort:
    """A minimal in-memory :class:`VoicePort` for tests.

    Records what was played and the latest ``on_finished`` callback so a test can
    simulate a track ending naturally via :meth:`finish_current`.
    """

    def __init__(self) -> None:
        self.played: list[tuple[str, float]] = []
        self.stop_count = 0
        self._playing = False
        self._on_finished: TrackFinishedCallback | None = None

    async def join(self, channel_id: str) -> None:  # pragma: no cover - unused by skill
        pass

    async def play(
        self,
        source_url: str,
        *,
        volume: float = 0.6,
        on_finished: TrackFinishedCallback | None = None,
    ) -> None:
        self.played.append((source_url, volume))
        self._on_finished = on_finished
        self._playing = True

    async def stop(self) -> None:
        self.stop_count += 1
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    @property
    def pending_callback(self) -> TrackFinishedCallback | None:
        return self._on_finished

    async def finish_current(self) -> None:
        """Simulate the current track ending on its own."""
        callback = self._on_finished
        self._playing = False
        if callback is not None:
            await callback()


async def test_play_starts_immediately_when_idle() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice)
    result = await MusicSkill().run({"action": "play", "query": "song-a"}, ctx)
    assert "Now playing" in (result.text or "")
    assert voice.played == [("song-a", 0.6)]


async def test_second_play_enqueues() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice)
    skill = MusicSkill()
    await skill.run({"action": "play", "query": "song-a"}, ctx)
    result = await skill.run({"action": "play", "query": "song-b"}, ctx)
    assert "Enqueued" in (result.text or "")
    assert len(voice.played) == 1  # second one is queued, not played yet


async def test_requester_can_self_skip_to_next() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice, user_id="owner")
    skill = MusicSkill()
    await skill.run({"action": "play", "query": "song-a"}, ctx)
    await skill.run({"action": "play", "query": "song-b"}, ctx)
    result = await skill.run({"action": "skip"}, ctx)
    assert "Now playing" in (result.text or "")
    assert voice.played[-1][0] == "song-b"


async def test_skip_requires_votes_from_non_requesters() -> None:
    voice = FakeVoicePort()
    skill = MusicSkill()
    owner_ctx = make_context(supports_voice=True, voice=voice, user_id="owner")
    await skill.run({"action": "play", "query": "song-a"}, owner_ctx)

    for i in range(SKIP_THRESHOLD - 1):
        voter = make_context(supports_voice=True, voice=voice, user_id=f"voter-{i}")
        result = await skill.run({"action": "skip"}, voter)
        assert "Skip vote added" in (result.text or "")

    final_voter = make_context(supports_voice=True, voice=voice, user_id="voter-final")
    result = await skill.run({"action": "skip"}, final_voter)
    assert "Skipped" in (result.text or "")


async def test_stop_clears_and_disconnects() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice)
    skill = MusicSkill()
    await skill.run({"action": "play", "query": "song-a"}, ctx)
    result = await skill.run({"action": "stop"}, ctx)
    assert "Stopped" in (result.text or "")
    assert voice.stop_count == 1


async def test_play_without_voice_capability_fails() -> None:
    result = await MusicSkill().run({"action": "play", "query": "x"}, make_context())
    assert result.is_error


async def test_queue_auto_advances_when_track_finishes() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice)
    skill = MusicSkill()
    await skill.run({"action": "play", "query": "song-a"}, ctx)
    await skill.run({"action": "play", "query": "song-b"}, ctx)

    # song-a ends on its own -> song-b should start automatically.
    await voice.finish_current()

    assert [url for url, _ in voice.played] == ["song-a", "song-b"]
    queue_view = await skill.run({"action": "queue"}, ctx)
    assert "song-b" in (queue_view.text or "")


async def test_auto_advance_stops_when_queue_empty() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice)
    skill = MusicSkill()
    await skill.run({"action": "play", "query": "only-song"}, ctx)

    await voice.finish_current()  # nothing queued

    assert not voice.is_playing()
    queue_view = await skill.run({"action": "queue"}, ctx)
    assert "empty" in (queue_view.text or "").lower()


async def test_stale_finished_callback_is_ignored_after_manual_skip() -> None:
    voice = FakeVoicePort()
    ctx = make_context(supports_voice=True, voice=voice, user_id="owner")
    skill = MusicSkill()
    await skill.run({"action": "play", "query": "song-a"}, ctx)
    await skill.run({"action": "play", "query": "song-b"}, ctx)

    # Capture song-a's finished-callback, then skip to song-b manually.
    stale_callback = voice.pending_callback
    assert stale_callback is not None
    await skill.run({"action": "skip"}, ctx)
    assert voice.played[-1][0] == "song-b"

    # song-a's teardown fires its (now stale) callback late: it must be ignored,
    # not advance past song-b.
    await stale_callback()

    assert [url for url, _ in voice.played] == ["song-a", "song-b"]  # no third play
    queue_view = await skill.run({"action": "queue"}, ctx)
    assert "song-b" in (queue_view.text or "")
