"""The local chat harness: replays a conversation through the core, with no Discord."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from petbot.domain import (
    EmbedSpec,
    Input,
    Recalled,
    Role,
    Skill,
    SkillContext,
    SkillResult,
    TextInput,
)
from petbot.frontends.discord.render import SERVICE_UNREACHABLE
from petbot.platform import LambdaTransport, ProcessClient, ToolRegistry
from petbot.process import ChatProcess
from petbot.services.core.chat import (
    BOT_NAME,
    ChainSettings,
    Conversation,
    Deployed,
    InProcess,
    Message,
    _conversation,
    _core,
    _parse,
    context_for,
    replay,
)
from petbot.types import MathArgs

_CONVERSATIONS = Path(__file__).parents[3] / "conversations"


class _Recorder:
    """A process that answers from ``replies`` in order (numbered replies when it runs out),
    raising any exception it is given, and keeps every input it saw."""

    def __init__(self, *replies: SkillResult | Exception) -> None:
        self.seen: list[tuple[TextInput, SkillContext]] = []
        self._replies = list(replies)

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        assert isinstance(inp, TextInput)
        self.seen.append((inp, ctx))
        reply = self._replies.pop(0) if self._replies else None
        if isinstance(reply, Exception):
            raise reply
        return reply or SkillResult.message(f"reply {len(self.seen)}")

    def history(self, index: int) -> list[tuple[Role, str, str]]:
        history = self.seen[index][0].history
        assert isinstance(history, Recalled)
        return [(t.role, t.author, t.text) for t in history.turns]


def _conversation_of(*messages: Message, **place: object) -> Conversation:
    return Conversation.model_validate({**place, "messages": [m.model_dump() for m in messages]})


async def _replay(
    process: object, conversation: Conversation, *, max_turns: int = 25, seconds: float = 30
) -> tuple[list[str], str]:
    out = io.StringIO()
    replies = await replay(
        InProcess(process, seconds=seconds),  # type: ignore[arg-type]
        conversation,
        out,
        max_turns=max_turns,
        verbose=True,
    )
    return replies, out.getvalue()


async def test_replay_sends_each_message_with_the_chain_before_it() -> None:
    process = _Recorder()
    replies, _ = await _replay(
        process,
        _conversation_of(
            Message(author="Ann", text="hi bot"),
            Message(author="Bo", text="psst, Ann", to_bot=False),
            Message(author="Ann", text="  again  "),
        ),
    )
    assert replies == ["reply 1", "reply 2"]
    assert [inp.text for inp, _ in process.seen] == ["hi bot", "again"]
    assert process.history(0) == []
    assert process.history(1) == [
        (Role.USER, "Ann", "hi bot"),
        (Role.ASSISTANT, BOT_NAME, "reply 1"),
        (Role.USER, "Bo", "psst, Ann"),
    ]
    assert process.seen[1][1].user.display_name == "Ann"


async def test_a_fresh_mention_starts_a_new_chain() -> None:
    process = _Recorder()
    await _replay(
        process,
        _conversation_of(
            Message(author="Ann", text="one"), Message(author="Ann", text="two", fresh=True)
        ),
    )
    assert process.history(1) == []


async def test_history_is_capped_at_the_frontends_reply_chain_depth() -> None:
    process = _Recorder()
    chatter = [Message(author="Bo", text=f"m{i}", to_bot=False) for i in range(5)]
    await _replay(
        process, _conversation_of(*chatter, Message(author="Ann", text="go")), max_turns=3
    )
    assert [text for _, _, text in process.history(0)] == ["m2", "m3", "m4"]


async def test_a_reply_split_across_messages_restarts_the_chain_at_its_last() -> None:
    long = "\n".join(f"line {i} " + "x" * 90 for i in range(40))  # over Discord's 2000
    process = _Recorder(SkillResult.message(long))
    replies, _ = await _replay(
        process,
        _conversation_of(Message(author="Ann", text="essay?"), Message(author="Ann", text="ok")),
    )
    ((role, author, text),) = process.history(1)  # the last message of the reply, alone
    assert (role, author) == (Role.ASSISTANT, BOT_NAME)
    assert replies[0].endswith(text) and len(text) < len(long)


async def test_history_reads_a_reply_back_as_the_frontend_does() -> None:
    card = EmbedSpec(title="results", image_url="https://img/x.png")
    process = _Recorder(
        SkillResult.message("here~", embed=card),
        SkillResult.message(None, embed=card),
        SkillResult.message("see `https://a.test/x`"),
    )
    _, out = await _replay(
        process,
        _conversation_of(*(Message(author="Ann", text=t) for t in ("a", "b", "c", "d"))),
    )
    assert [text for role, _, text in process.history(3) if role is Role.ASSISTANT] == [
        "here~",
        "[image] results — https://img/x.png",
        "see https://a.test/x",
    ]
    assert "  [image] results — https://img/x.png" in out.splitlines()


async def test_an_unexpected_error_gets_productions_reply_and_the_chain_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    process = _Recorder(RuntimeError("model endpoint down"))
    replies, _ = await _replay(
        process,
        _conversation_of(Message(author="Ann", text="hi"), Message(author="Ann", text="again")),
    )
    assert replies == ["Something went wrong handling that request.", "reply 2"]
    assert "Process raised" in caplog.text


def _math_then_answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
        return ModelResponse(parts=[TextPart(content="it's 42~")])
    return ModelResponse(
        parts=[
            ToolCallPart(tool_name="math", args={"expression": "6*7"}),
            ToolCallPart(tool_name="no_such_tool", args={}),
        ]
    )


async def test_tool_calls_come_from_the_agent_run_with_what_the_model_got_back() -> None:
    chat = ChatProcess(ToolRegistry.from_installed_skills(), model=FunctionModel(_math_then_answer))
    replies, out = await _replay(chat, _conversation_of(Message(author="Ann", text="6*7?")))
    assert replies == ["it's 42~"]
    lines = out.splitlines()
    assert '  [math] {"expression":"6*7"}' in lines
    assert any(line.strip().startswith(">>>") and "6*7" in line for line in lines)
    assert "  [no_such_tool] {} (rejected; the model was asked to retry)" in lines
    assert any("Unknown tool name" in line for line in lines)


class _SlowMath(Skill[MathArgs]):
    name = "math"
    description = "Evaluate an arithmetic expression."
    args_model = MathArgs

    async def run(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        await asyncio.sleep(5)
        return SkillResult.message("too late")


def _math_forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name="math", args={"expression": "1+1"})])


async def test_a_call_cut_off_by_the_turns_budget_is_still_shown() -> None:
    chat = ChatProcess(ToolRegistry([_SlowMath()]), model=FunctionModel(_math_forever))
    replies, out = await _replay(
        chat, _conversation_of(Message(author="Ann", text="1+1?")), seconds=0.2
    )
    assert "took me too long" in replies[0]
    assert '  [math] {"expression":"1+1"} (no result: the turn ended first)' in out.splitlines()


def test_context_carries_the_place_and_the_age_gate() -> None:
    conversation = _conversation_of(Message(author="Ann", text="x"), server="YEEN", nsfw=True)
    ctx = context_for(conversation, "Ann")
    assert (ctx.community_name, ctx.channel_name, ctx.allows_explicit) == ("YEEN", "general", True)
    dm = context_for(_conversation_of(Message(author="Ann", text="x"), server=None), "Ann")
    assert (dm.community_name, dm.channel_name) == (None, None)


def test_chain_depth_is_the_frontends_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HISTORY_MAX_TURNS", raising=False)
    assert ChainSettings(_env_file=None).history_max_turns == 25
    monkeypatch.setenv("HISTORY_MAX_TURNS", "7")
    assert ChainSettings(_env_file=None).history_max_turns == 7


@pytest.mark.parametrize("path", sorted(_CONVERSATIONS.glob("*.json")), ids=lambda p: p.name)
def test_shipped_conversations_parse(path: Path) -> None:
    assert Conversation.model_validate_json(path.read_text("utf-8")).messages


def test_cli_takes_a_file_or_a_message(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        _parse([])
    assert "give a conversation file or --say" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        _parse(["c.json", "--say", "hi"])
    assert "not both" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        _parse(["c.json", "--nsfw"])
    assert "go with --say" in capsys.readouterr().err
    assert _parse(["--say", "hi"]).author == "tester"
    assert _parse(["--say", "hi", "--as", "Ann"]).author == "Ann"


def test_a_blank_message_or_a_missing_file_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Not a valid conversation"):
        _conversation(_parse(["--say", "   "]))
    with pytest.raises(SystemExit, match="Can't read"):
        _conversation(_parse([str(tmp_path / "missing.json")]))


def test_message_text_is_stripped() -> None:
    assert Message(author="Ann", text="  hi \n").text == "hi"


class _FakeLambda:
    """A boto3 Lambda client stand-in that answers each invoke from ``replies`` and keeps
    every payload it was sent."""

    def __init__(self, *replies: SkillResult | str) -> None:
        self.payloads: list[dict[str, Any]] = []
        self._replies = list(replies)

    def invoke(self, **kwargs: Any) -> Any:
        self.payloads.append(json.loads(kwargs["Payload"]))
        reply = self._replies.pop(0)
        if isinstance(reply, str):
            return {"FunctionError": reply, "Payload": io.BytesIO(b'{"errorMessage": "boom"}')}
        return {"Payload": io.BytesIO(reply.model_dump_json().encode())}

    def get_waiter(self, waiter_name: str) -> Any:
        raise AssertionError("the function is Active")


async def test_a_deployed_core_gets_the_dispatch_the_frontend_sends() -> None:
    client = _FakeLambda(SkillResult.message("hi from dev"), SkillResult.message("again"))
    core = Deployed(ProcessClient(LambdaTransport("petbot-dev-core", client)))
    out = io.StringIO()
    replies = await replay(
        core,
        _conversation_of(Message(author="Ann", text="hi"), Message(author="Ann", text="more")),
        out,
        max_turns=25,
    )
    assert replies == ["hi from dev", "again"]
    first, second = client.payloads
    assert first["input"]["text"] == "hi"
    assert first["context"]["user"]["display_name"] == "Ann"
    assert [t["text"] for t in second["input"]["history"]["turns"]] == ["hi", "hi from dev"]
    assert out.getvalue().splitlines()[:2] == ["Ann: hi", f"{BOT_NAME}: hi from dev"]


async def test_a_failed_dispatch_gets_the_frontends_reply_and_the_chain_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeLambda("Unhandled", SkillResult.message("back"))
    core = Deployed(ProcessClient(LambdaTransport("petbot-dev-core", client)))
    replies = await replay(
        core,
        _conversation_of(Message(author="Ann", text="hi"), Message(author="Ann", text="again")),
        io.StringIO(),
        max_turns=25,
    )
    assert replies == [SERVICE_UNREACHABLE, "back"]
    assert "dispatch failed" in caplog.text


def test_lambda_sends_to_a_deployed_core(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clients: list[str] = []
    monkeypatch.setattr("boto3.client", lambda service, **kw: clients.append(service))
    assert isinstance(_core(_parse(["--say", "hi", "--lambda", "petbot-dev-core"])), Deployed)
    assert clients == ["lambda"]
    for flag in (["--timeout", "60"], ["-v"]):
        with pytest.raises(SystemExit):
            _parse(["--say", "hi", "--lambda", "petbot-dev-core", *flag])
        assert "a deployed core keeps its own" in capsys.readouterr().err
    assert _parse(["--say", "hi"]).timeout == 120
