"""Tests for the neutral music skill, driven through a fake VoicePort."""

from __future__ import annotations

from conftest import make_context

from petbot.core.skills.music_skill import SKIP_THRESHOLD, MusicSkill


class FakeVoicePort:
    """A minimal in-memory :class:`VoicePort` for tests."""

    def __init__(self) -> None:
        self.played: list[tuple[str, float]] = []
        self.stop_count = 0
        self._playing = False

    async def join(self, channel_id: str) -> None:  # pragma: no cover - unused by skill
        pass

    async def play(self, source_url: str, *, volume: float = 0.6) -> None:
        self.played.append((source_url, volume))
        self._playing = True

    async def stop(self) -> None:
        self.stop_count += 1
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing


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

    # Distinct voters in the same conversation.
    for i in range(SKIP_THRESHOLD - 1):
        voter = make_context(
            supports_voice=True, voice=voice, user_id=f"voter-{i}", conversation_id="conv-1"
        )
        owner_ctx_conv = make_context(
            supports_voice=True, voice=voice, user_id="owner", conversation_id="conv-1"
        )
        # ensure same conversation as owner
        assert owner_ctx_conv.conversation_id == owner_ctx.conversation_id
        result = await skill.run({"action": "skip"}, voter)
        assert "Skip vote added" in (result.text or "")

    final_voter = make_context(
        supports_voice=True, voice=voice, user_id="voter-final", conversation_id="conv-1"
    )
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
