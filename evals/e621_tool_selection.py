"""Eval: does the agent actually *call* the e621 tool when asked for an e621 image?

This is the regression behind the observability work — PetBot silently *not* calling e621.
The dataset is deterministic and constructs offline (so CI can check it is well-formed), but
running it needs a real ``CHAT_LLM`` provider: ``TestModel`` always calls the tools you name,
so it cannot judge selection. Run against the configured model with::

    uv run python -m evals.e621_tool_selection

It builds a registry of *recording* skills (no network), runs the chat agent over each case,
and scores whether the expected tool was chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from petbot.domain import Platform, Skill, SkillContext, SkillResult, TextInput, User
from petbot.platform import ToolRegistry
from petbot.process import ChatProcess
from petbot.process.model import build_model
from petbot.process.settings import ChatSettings
from petbot.types import BooruArgs, MathArgs


class Turn(BaseModel):
    """One eval input: a user message and whether the channel is age-gated."""

    prompt: str
    allows_explicit: bool


class Outcome(BaseModel):
    """What the agent did: the tool names it called, in order."""

    tools: list[str]


@dataclass
class CalledTool(Evaluator[Turn, Outcome]):
    """Pass when the expected tool name appears in the agent's tool calls."""

    expected: str

    def evaluate(self, ctx: EvaluatorContext[Turn, Outcome]) -> bool:
        return self.expected in ctx.output.tools


@dataclass
class _Recorder(Skill[BaseModel]):
    """A tool that records that it was called and returns a canned image card."""

    name: str
    args_model: type[BaseModel]
    sink: list[str] = field(default_factory=list)
    description: str = "record calls"

    async def run(self, args: BaseModel, ctx: SkillContext) -> SkillResult:
        self.sink.append(self.name)
        return SkillResult.message("ok")


def build_dataset() -> Dataset[Turn, Outcome]:
    """The cases: an e621 request in an SFW channel and in an NSFW channel must both call e621."""
    return Dataset[Turn, Outcome](
        name="e621_tool_selection",
        cases=[
            Case(
                name="e621_sfw_channel",
                inputs=Turn(prompt="show me a husky from e621", allows_explicit=False),
                evaluators=[CalledTool(expected="e621")],
            ),
            Case(
                name="e621_nsfw_channel",
                inputs=Turn(prompt="grab me an explicit husky off e621", allows_explicit=True),
                evaluators=[CalledTool(expected="e621")],
            ),
        ],
    )


async def run_turn(turn: Turn) -> Outcome:
    """Run one turn through the chat agent against the configured model, recording tool calls."""
    sink: list[str] = []
    registry = ToolRegistry(
        [
            _Recorder(name="e621", args_model=BooruArgs, sink=sink),
            _Recorder(name="derpi", args_model=BooruArgs, sink=sink),
            _Recorder(name="math", args_model=MathArgs, sink=sink),
        ]
    )
    settings = ChatSettings()
    chat = ChatProcess(registry, model=build_model(settings), settings=settings)
    ctx = SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="eval", display_name="eval"),
        conversation_id="discord:eval",
        allows_explicit=turn.allows_explicit,
    )
    await chat.respond(TextInput(text=turn.prompt), ctx)
    return Outcome(tools=sink)


def main() -> None:
    report = build_dataset().evaluate_sync(run_turn)
    report.print()


if __name__ == "__main__":
    main()
