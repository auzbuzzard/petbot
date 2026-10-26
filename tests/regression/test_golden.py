"""The golden cases and their grader, offline: every case is well-formed against the
catalog, and the grader passes and fails the trajectories it should."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from petbot.domain import CommandInput, EmbedSpec, SkillResult, TextInput, ToolCall
from petbot.frontends.discord.render import SERVICE_UNREACHABLE
from petbot.types import CATALOG

from .golden import Case, CaseReport, Trial, grade, load_cases, summary

CASES = load_cases()
COMMANDS = {c.name: c for c in CATALOG}


def _case(**fields: Any) -> Case:
    return Case.model_validate({"id": "t", "why": "test", **fields})


def _call(tool: str, outcome: str = "returned", output: str = "ok", **args: object) -> ToolCall:
    return ToolCall.model_validate(
        {"tool": tool, "args": args, "outcome": outcome, "output": output}
    )


def _reply(*calls: ToolCall, text: str = "here you go") -> SkillResult:
    return SkillResult(text=text, trajectory=calls)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_a_case_names_a_tool_and_arguments_it_has(case: Case) -> None:
    command = COMMANDS[case.expect.tool]
    assert set(case.expect.args) <= set(command.args_model.model_fields)
    if case.command is not None:
        assert command.slash, f"/{case.command} is not a slash command"
        command.args_model.model_validate(case.values)


def test_cases_cover_chat_and_slash() -> None:
    assert any(isinstance(c.input(), TextInput) for c in CASES)
    assert any(isinstance(c.input(), CommandInput) for c in CASES)


def test_case_ids_are_unique(tmp_path: Path) -> None:
    path = tmp_path / "cases.toml"
    path.write_text(
        '[[case]]\nid = "a"\nwhy = "x"\nsay = "hi"\nexpect = { tool = "math" }\n' * 2,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(path)


@pytest.mark.parametrize(
    "fields",
    [
        {"expect": {"tool": "math"}},
        {"say": "hi", "command": "math", "expect": {"tool": "math"}},
        {"command": "math", "expect": {"tool": "leetcode"}},
        {"say": "hi", "expect": {"tool": "math", "args": {"expression": {}}}},
        {"say": "hi", "expect": {"tool": "math", "args": {"expression": {"like": "x"}}}},
    ],
)
def test_a_malformed_case_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _case(**fields)


_RANDOM = _case(
    say="random problem", expect={"tool": "leetcode", "args": {"mode": {"iequals": "random"}}}
)


def test_the_expected_call_passes_whatever_the_wording() -> None:
    assert grade(_RANDOM, _reply(_call("leetcode", mode="random"), text="anything at all")) == []
    assert grade(_RANDOM, _reply(_call("leetcode", mode=" Random "))) == []


def test_a_call_without_a_required_argument_fails() -> None:
    assert grade(_RANDOM, _reply(_call("leetcode"))) == ["leetcode was called without mode"]


def test_the_wrong_argument_or_no_call_fails() -> None:
    assert grade(_RANDOM, _reply(_call("leetcode", mode="daily"))) != []
    assert grade(_RANDOM, _reply(_call("math", expression="1"))) == ["no leetcode call"]
    assert grade(_RANDOM, _reply()) == ["no leetcode call"]


def test_any_one_call_meeting_every_check_passes() -> None:
    reply = _reply(_call("leetcode", mode="daily"), _call("leetcode", mode="random"))
    assert grade(_RANDOM, reply) == []


def test_contains_checks_ignore_case() -> None:
    case = _case(
        say="weather",
        expect={"tool": "weather", "args": {"location": {"contains": ["paris"]}}},
    )
    assert grade(case, _reply(_call("weather", location="Paris, France"))) == []
    assert grade(case, _reply(_call("weather", location="London"))) != []
    any_of = _case(
        say="search",
        expect={"tool": "web_search", "args": {"query": {"contains_any": ["python", "cpython"]}}},
    )
    assert grade(any_of, _reply(_call("web_search", query="CPython release"))) == []
    assert grade(any_of, _reply(_call("web_search", query="ruby"))) != []


def test_an_upstream_failure_with_the_right_call_passes() -> None:
    case = _case(
        say="search", expect={"tool": "web_search", "args": {"query": {"contains": ["python"]}}}
    )
    call = _call("web_search", output="The skill reported: no results", query="python release")
    assert grade(case, _reply(call, text="I couldn't find anything, sorry!")) == []


def test_output_checks_read_the_tools_own_output() -> None:
    case = _case(say="6*7", expect={"tool": "math", "output_contains": ["42"]})
    assert grade(case, _reply(_call("math", output="<<<\t42", expression="6*7"))) == []
    assert grade(case, _reply(_call("math", output="<<<\t41", expression="6*7"))) != []
    rejected = _call("math", outcome="rejected", output="42 is not valid", expression="6*7")
    assert grade(case, _reply(rejected)) != []


def test_the_reply_must_not_be_empty_or_the_fallback() -> None:
    call = _call("leetcode", mode="random")
    assert grade(_RANDOM, _reply(call, text="  ")) != []
    assert grade(_RANDOM, _reply(call, text=SERVICE_UNREACHABLE)) != []
    card = SkillResult(embed=EmbedSpec(image_url="https://img/x.png"), trajectory=(call,))
    assert grade(_RANDOM, card) == []


def test_no_trajectory_fails() -> None:
    problems = grade(_RANDOM, SkillResult(text="hi"))
    assert len(problems) == 1 and problems[0].startswith("no trajectory")


def test_the_summary_counts_trials_and_shows_calls_in_one_table_cell() -> None:
    passing = Trial(_reply(_call("leetcode", mode="random")), ())
    piped = _reply(_call("web_search", query="a | b `c`"), text="hmm")
    failing = Trial(piped, ("no leetcode call",))
    crashed = Trial(None, ("the dispatch failed (RuntimeError)",))
    text = summary("petbot-dev-core", 3, [CaseReport(_RANDOM, (passing, failing, crashed))])
    assert "**0 of 1 cases passed.**" in text
    row = next(line for line in text.splitlines() if line.startswith("| `t`"))
    assert "| 1/3 |" in row
    assert '`leetcode {"mode":"random"}`' in row
    assert "a \\| b 'c'" in row
    assert "trial 2: no leetcode call" in text
    assert "trial 3: the dispatch failed (RuntimeError)" in text
