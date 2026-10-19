"""The tool registry, the serve boundary, the ProcessClient, and the HTTP + Lambda transports."""

from __future__ import annotations

import io
import json
from typing import Any

import httpx
import pytest
from botocore.exceptions import ClientError

from petbot.domain import (
    CommandInput,
    InvalidInput,
    Platform,
    Process,
    Skill,
    SkillContext,
    SkillError,
    SkillResult,
    User,
)
from petbot.platform import HttpTransport, LambdaTransport, ProcessClient, ToolRegistry, serve
from petbot.types import MathArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


class _EchoSkill(Skill[MathArgs]):
    name = "math"
    description = "echo"
    args_model = MathArgs

    async def run(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        return SkillResult.message(f"got {args.expression}")


# --- ToolRegistry -------------------------------------------------------------


async def test_registry_dispatch_validates_and_runs() -> None:
    registry = ToolRegistry([_EchoSkill()])
    result = await registry.dispatch("math", {"expression": "6 * 7"}, _ctx())
    assert result.text == "got 6 * 7"


async def test_registry_unknown_tool_raises_skill_error() -> None:
    registry = ToolRegistry([_EchoSkill()])
    with pytest.raises(SkillError):
        await registry.dispatch("nope", {"expression": "1"}, _ctx())


async def test_registry_bad_args_raise_invalid_input() -> None:
    registry = ToolRegistry([_EchoSkill()])
    with pytest.raises(InvalidInput):
        await registry.dispatch("math", {"not_expression": "x"}, _ctx())


def test_duplicate_skill_name_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry([_EchoSkill(), _EchoSkill()])


# --- serve + transport --------------------------------------------------------


class _EchoProcess(Process):
    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        assert isinstance(inp, CommandInput)
        return SkillResult.message(f"ran {inp.name}")


class _BoomProcess(Process):
    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        raise RuntimeError("kaboom")


def _body(inp: CommandInput) -> str:
    return json.dumps(
        {"input": inp.model_dump(mode="json"), "context": _ctx().model_dump(mode="json")}
    )


async def test_serve_decodes_runs_and_encodes() -> None:
    out = await serve(_EchoProcess(), _body(CommandInput(name="math", values={"expression": "1"})))
    assert SkillResult.model_validate_json(out).text == "ran math"


async def test_serve_maps_malformed_payload_to_result() -> None:
    # Missing fields and outright non-JSON both become a result — never an escaping error.
    assert SkillResult.model_validate_json(await serve(_EchoProcess(), '{"input": {}}')).text
    assert SkillResult.model_validate_json(await serve(_EchoProcess(), "not json")).text


async def test_serve_catches_unexpected_exception() -> None:
    out = await serve(_BoomProcess(), _body(CommandInput(name="math", values={})))
    assert SkillResult.model_validate_json(out).text  # a generic crash result, not a raise


async def test_process_client_http_round_trip() -> None:
    process = _EchoProcess()

    async def _handler(request: httpx.Request) -> httpx.Response:
        out = await serve(process, request.content)
        return httpx.Response(200, content=out)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://svc") as client:
        client_process: Process = ProcessClient(HttpTransport("http://svc/dispatch", client))
        result = await client_process.respond(
            CommandInput(name="math", values={"expression": "6 * 7"}), _ctx()
        )
    assert result.text == "ran math"


# --- LambdaTransport ----------------------------------------------------------


def _not_ready(code: str) -> ClientError:
    message = "The function is currently in the following state: Inactive"
    return ClientError({"Error": {"Code": code, "Message": message}}, "Invoke")


class _FakeLambda:
    """A boto3 Lambda client stand-in: raises each queued error, then serves the dispatch."""

    def __init__(self, *errors: Exception, function_error: str | None = None) -> None:
        self._errors = list(errors)
        self._function_error = function_error
        self.calls = 0

    def invoke(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        if self._function_error is not None:
            body = b'{"errorMessage": "Task timed out after 60.00 seconds"}'
            return {"FunctionError": self._function_error, "Payload": io.BytesIO(body)}
        return {"Payload": io.BytesIO(SkillResult.message("ran").model_dump_json().encode())}


def _command() -> CommandInput:
    return CommandInput(name="math", values={"expression": "1"})


@pytest.mark.parametrize("code", ["ResourceConflictException", "ResourceNotReadyException"])
async def test_lambda_transport_waits_out_a_function_that_is_not_active(code: str) -> None:
    # A container-image function idle for ~2 weeks goes Inactive: the next invoke is rejected
    # while Lambda re-pulls the image. That rejection must not become the user's answer.
    client = _FakeLambda(_not_ready(code), _not_ready(code))
    transport = LambdaTransport("petbot-core", client, retry_delay=0)
    result = await ProcessClient(transport).respond(_command(), _ctx())
    assert result.text == "ran"
    assert client.calls == 3


async def test_lambda_transport_gives_up_after_the_ready_timeout() -> None:
    client = _FakeLambda(*[_not_ready("ResourceConflictException")] * 10)
    transport = LambdaTransport("petbot-core", client, ready_timeout=0, retry_delay=0.01)
    with pytest.raises(ClientError):
        await ProcessClient(transport).respond(_command(), _ctx())
    assert client.calls == 1


async def test_lambda_transport_does_not_retry_other_errors() -> None:
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Invoke")
    client = _FakeLambda(denied)
    with pytest.raises(ClientError):
        await ProcessClient(LambdaTransport("petbot-core", client, retry_delay=0)).respond(
            _command(), _ctx()
        )
    assert client.calls == 1


async def test_lambda_transport_raises_the_runtime_error_on_function_error() -> None:
    client = _FakeLambda(function_error="Unhandled")
    with pytest.raises(RuntimeError, match="Task timed out"):
        await ProcessClient(LambdaTransport("petbot-core", client)).respond(_command(), _ctx())
