"""The regression suite's golden cases (``cases.toml``), their grader and its report.

A case is graded on the trajectory the deployed core reports (the tool calls behind the
answer, :attr:`~petbot.domain.result.SkillResult.trajectory`) and on the reply's shape,
never on its wording: the same code may word a reply differently on each run.
"""

from __future__ import annotations

import html
import json
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from petbot.domain import (
    CommandInput,
    Input,
    Platform,
    SkillContext,
    SkillResult,
    TextInput,
    ToolCall,
    User,
)
from petbot.frontends.discord.render import SERVICE_UNREACHABLE

CASES_FILE = Path(__file__).with_name("cases.toml")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArgCheck(_Strict):
    """Constraints on one argument of the expected call; each one given must hold."""

    equals: str | int | float | bool | None = None
    #: The same string, ignoring case and surrounding space (as the skills read it).
    iequals: str | None = None
    #: Every one of these substrings, ignoring case.
    contains: tuple[str, ...] = ()
    #: At least one of these substrings, ignoring case.
    contains_any: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _checks_something(self) -> ArgCheck:
        if self.equals is None and self.iequals is None and not self.contains + self.contains_any:
            raise ValueError("an argument check needs a constraint")
        return self

    def problems(self, name: str, value: object) -> list[str]:
        found: list[str] = []
        text = value.strip().lower() if isinstance(value, str) else None
        if self.equals is not None and value != self.equals:
            found.append(f"{name}={value!r}, expected {self.equals!r}")
        if self.iequals is not None and text != self.iequals.strip().lower():
            found.append(f"{name}={value!r}, expected {self.iequals!r}")
        missing = [s for s in self.contains if text is None or s.lower() not in text]
        if missing:
            found.append(f"{name}={value!r} lacks {missing}")
        if self.contains_any and not any(
            text is not None and s.lower() in text for s in self.contains_any
        ):
            found.append(f"{name}={value!r} has none of {list(self.contains_any)}")
        return found


class Expect(_Strict):
    """The call a case requires: some call to ``tool`` meets every check."""

    tool: str
    args: dict[str, ArgCheck] = Field(default_factory=dict)
    #: Substrings of the tool's own output. Only for output computed in the core (math),
    #: never a third party's answer, which may change or fail.
    output_contains: tuple[str, ...] = ()


class Case(_Strict):
    id: str
    #: The behaviour this case guards, and where it came from.
    why: str
    #: A chat message, sent as an @mention.
    say: str | None = None
    #: Or a slash command and its option values.
    command: str | None = None
    values: dict[str, object] = Field(default_factory=dict)
    nsfw: bool = False
    expect: Expect

    @model_validator(mode="after")
    def _one_input(self) -> Case:
        if (self.say is None) == (self.command is None):
            raise ValueError(f"{self.id}: give `say` or `command`, not both or neither")
        if self.say is not None and self.values:
            raise ValueError(f"{self.id}: `values` go with `command`")
        if self.command is not None and self.expect.tool != self.command:
            raise ValueError(f"{self.id}: a slash command calls its own tool")
        return self

    def input(self) -> Input:
        if self.say is not None:
            return TextInput(text=self.say)
        assert self.command is not None
        return CommandInput(name=self.command, values=dict(self.values))

    def context(self) -> SkillContext:
        return SkillContext(
            platform=Platform.DISCORD,
            user=User(platform=Platform.DISCORD, id="regression:tester", display_name="tester"),
            conversation_id=f"regression:{self.id}",
            allows_explicit=self.nsfw,
            community_name="Regression tests",
            channel_name="general",
        )


class _CasesFile(_Strict):
    case: tuple[Case, ...]


def load_cases(path: Path = CASES_FILE) -> tuple[Case, ...]:
    with path.open("rb") as file:
        cases = _CasesFile.model_validate(tomllib.load(file)).case
    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate case ids: {duplicates}")
    return cases


def _call_problems(expect: Expect, call: ToolCall) -> list[str]:
    found: list[str] = []
    for name, check in expect.args.items():
        if name not in call.args:
            found.append(f"{call.tool} was called without {name}")
        else:
            found.extend(check.problems(name, call.args[name]))
    if expect.output_contains:
        output = (call.output or "").lower() if call.outcome == "returned" else ""
        missing = [s for s in expect.output_contains if s.lower() not in output]
        if missing:
            found.append(f"{call.tool}'s output lacks {missing}")
    return found


def grade(case: Case, result: SkillResult) -> list[str]:
    """Why ``result`` fails ``case``; empty when it passes."""
    found: list[str] = []
    if result.text == SERVICE_UNREACHABLE:
        found.append("the reply is the frontend's fallback (SERVICE_UNREACHABLE)")
    if not (result.text or "").strip() and result.embed is None:
        found.append("the reply is empty")
    if result.trajectory is None:
        found.append(
            "no trajectory: the core reports none (CORE_REPORT_TRAJECTORY is off), "
            "or the turn crashed or ran out of time (see the reply)"
        )
        return found
    calls = [c for c in result.trajectory if c.tool == case.expect.tool]
    if not calls:
        found.append(f"no {case.expect.tool} call")
        return found
    # Some call must meet every check; otherwise report the call that came closest.
    closest = min((_call_problems(case.expect, c) for c in calls), key=len)
    return found + closest


@dataclass(frozen=True)
class Trial:
    result: SkillResult | None
    problems: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class CaseReport:
    case: Case
    trials: tuple[Trial, ...]

    @property
    def passes(self) -> int:
        return sum(t.passed for t in self.trials)


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def describe(call: ToolCall) -> str:
    args = json.dumps(call.args, ensure_ascii=False, separators=(",", ":"))
    note = "" if call.outcome == "returned" else f" ({call.outcome})"
    return f"{call.tool} {_clip(args, 120)}{note}"


def _cell(text: str) -> str:
    """``text`` as one markdown table cell's code span."""
    return "`" + text.replace("`", "'").replace("|", "\\|") + "`"


def _calls(trial: Trial) -> str:
    if trial.result is None:
        return "*dispatch failed*"
    if trial.result.trajectory is None:
        return "*none reported*"
    if not trial.result.trajectory:
        return "*no tool call*"
    return ", ".join(_cell(describe(c)) for c in trial.result.trajectory)


def summary(function: str, trials: int, reports: Sequence[CaseReport]) -> str:
    """The job summary: each case's passing trials and the tool calls each trial made,
    then why each failing trial failed. Tool arguments and outputs, never exception text."""
    passed = sum(r.passes == len(r.trials) for r in reports)
    lines = [
        f"### Regression suite on `{function}`",
        "",
        f"Each case ran {trials} time(s) and passes only if every trial passed (pass^{trials}). "
        f"**{passed} of {len(reports)} cases passed.**",
        "",
        "| Case | Trials passed | Tool calls, per trial |",
        "|---|---|---|",
    ]
    for report in reports:
        calls = "<br>".join(f"{n}: {_calls(t)}" for n, t in enumerate(report.trials, 1))
        lines.append(
            f"| `{report.case.id}` | {report.passes}/{len(report.trials)} | {calls or '-'} |"
        )
    failures = [(r, n, t) for r in reports for n, t in enumerate(r.trials, 1) if not t.passed]
    if failures:
        lines += ["", "#### Failed trials", ""]
    for report, number, trial in failures:
        lines.append(f"**`{report.case.id}`**, trial {number}: " + "; ".join(trial.problems))
        lines.append("")
        if trial.result is not None:
            details = [f"reply: {_clip(trial.result.text or '', 300)}"]
            for call in trial.result.trajectory or ():
                details.append(f"{describe(call)} -> {_clip(call.output or '', 200)}")
            lines.append("<pre>" + html.escape("\n".join(details)) + "</pre>")
            lines.append("")
    return "\n".join(lines) + "\n"
