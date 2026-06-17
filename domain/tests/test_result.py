"""SkillResult constructors and the expected-failure flag."""

from __future__ import annotations

from petbot_domain import EmbedSpec, SkillResult


def test_message_is_not_an_error() -> None:
    result = SkillResult.message("hi", embed=EmbedSpec(title="t"))
    assert not result.is_error
    assert result.text == "hi"
    assert result.embed is not None
    assert result.embed.title == "t"


def test_failure_sets_error() -> None:
    result = SkillResult.failure("nope")
    assert result.is_error
    assert result.error == "nope"
    assert result.text is None


def test_files_default_empty() -> None:
    assert SkillResult.message().files == ()
