"""The command catalog: typed entries the slash surface and the agent both derive from."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from petbot.types import CATALOG
from petbot.types.args import (
    BooruArgs,
    LeetCodeArgs,
    MathArgs,
    WeatherArgs,
    WebFetchArgs,
    WebSearchArgs,
)


def test_catalog_holds_the_command_skills_only() -> None:
    names = {c.name for c in CATALOG}
    assert names == {"math", "derpi", "e621", "web_search", "web_fetch", "weather", "leetcode"}
    # music (a separate service) and chat (the process itself) are absent by design.
    assert "music" not in names and "chat" not in names


def test_catalog_binds_each_name_to_its_args_model() -> None:
    by_name = {c.name: c for c in CATALOG}
    assert by_name["math"].args_model is MathArgs
    assert by_name["derpi"].args_model is BooruArgs
    assert by_name["e621"].args_model is BooruArgs
    assert by_name["leetcode"].args_model is LeetCodeArgs


def test_research_tools_are_agent_only() -> None:
    by_name = {c.name: c for c in CATALOG}
    assert by_name["web_search"].args_model is WebSearchArgs
    assert by_name["web_fetch"].args_model is WebFetchArgs
    assert by_name["weather"].args_model is WeatherArgs
    slash = {c.name for c in CATALOG if c.slash}
    # leetcode returns a finished answer, so it is a slash command too.
    assert slash == {"math", "derpi", "e621", "leetcode"}


def test_leetcode_args_default_to_the_daily_and_bound_their_choices() -> None:
    assert LeetCodeArgs().effective_mode == "daily"
    # A difficulty with no mode is a random problem of it, never the daily.
    assert LeetCodeArgs(difficulty="easy").effective_mode == "random"
    assert LeetCodeArgs(mode="daily", difficulty="easy").effective_mode == "daily"
    with pytest.raises(ValidationError):
        LeetCodeArgs.model_validate({"mode": "random", "difficulty": "impossible"})


def test_leetcode_args_accept_leetcodes_own_spelling() -> None:
    # Results say "Easy"; a model echoing that back must still validate.
    args = LeetCodeArgs.model_validate({"mode": " Random", "difficulty": "Easy"})
    assert args == LeetCodeArgs(mode="random", difficulty="easy")
