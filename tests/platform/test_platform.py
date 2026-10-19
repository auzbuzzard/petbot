"""The tool registry, the serve boundary, the ProcessClient, the HTTP + Lambda transports, and
request claiming."""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

import httpx
import pytest
from botocore.exceptions import ClientError, WaiterError

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
from petbot.platform import (
    ClaimingProcess,
    DynamoClaims,
    HttpTransport,
    LambdaTransport,
    Phase,
    ProcessClient,
    ToolRegistry,
    observe,
    serve,
)
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


class _FakeWaiter:
    def __init__(self, client: _FakeLambda, error: Exception | None) -> None:
        self._client = client
        self._error = error

    def wait(self, **kwargs: Any) -> None:
        self._client.waits.append(kwargs)
        if self._error is not None:
            raise self._error
        self._client.active = True


class _FakeLambda:
    """A boto3 Lambda client stand-in: rejects invokes until its waiter has seen the
    function Active, then serves the dispatch."""

    def __init__(
        self,
        *,
        active: bool = True,
        not_ready_code: str = "ResourceConflictException",
        invoke_error: Exception | None = None,
        waiter_error: Exception | None = None,
        function_error: str | None = None,
    ) -> None:
        self.active = active
        self._not_ready_code = not_ready_code
        self._invoke_error = invoke_error
        self._waiter_error = waiter_error
        self._function_error = function_error
        self.calls = 0
        self.waits: list[dict[str, Any]] = []
        self.waiter_names: list[str] = []

    def invoke(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self._invoke_error is not None:
            raise self._invoke_error
        if not self.active:
            raise _not_ready(self._not_ready_code)
        if self._function_error is not None:
            body = b'{"errorMessage": "Task timed out after 60.00 seconds"}'
            return {"FunctionError": self._function_error, "Payload": io.BytesIO(body)}
        return {"Payload": io.BytesIO(SkillResult.message("ran").model_dump_json().encode())}

    def get_waiter(self, waiter_name: str) -> _FakeWaiter:
        self.waiter_names.append(waiter_name)
        return _FakeWaiter(self, self._waiter_error)


def _command() -> CommandInput:
    return CommandInput(name="math", values={"expression": "1"})


async def _send(client: _FakeLambda, **kwargs: Any) -> SkillResult:
    transport = LambdaTransport("petbot-core", client, **kwargs)
    return await ProcessClient(transport).respond(_command(), _ctx())


@pytest.mark.parametrize("code", ["ResourceConflictException", "ResourceNotReadyException"])
async def test_lambda_transport_waits_out_a_function_that_is_not_active(code: str) -> None:
    # A container-image function idle for ~2 weeks goes Inactive: the next invoke is rejected
    # while Lambda re-pulls the image. That rejection must not become the user's answer.
    client = _FakeLambda(active=False, not_ready_code=code)
    result = await _send(client, ready_timeout=10)
    assert result.text == "ran"
    assert client.calls == 2  # the rejected invoke, then one after the wait
    assert client.waiter_names == ["function_active"]
    assert client.waits[0]["FunctionName"] == "petbot-core"
    # The waiter's budget is the ready timeout: 2 s polls, 5 of them.
    assert client.waits[0]["WaiterConfig"] == {"Delay": 2, "MaxAttempts": 5}


async def test_lambda_transport_gives_up_when_the_function_never_becomes_active() -> None:
    timeout = WaiterError("FunctionActive", "Max attempts exceeded", {})
    client = _FakeLambda(active=False, waiter_error=timeout)
    with pytest.raises(WaiterError):
        await _send(client, ready_timeout=10)
    assert client.calls == 1


async def test_lambda_transport_does_not_wait_on_other_errors() -> None:
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Invoke")
    client = _FakeLambda(invoke_error=denied)
    with pytest.raises(ClientError):
        await _send(client)
    assert (client.calls, client.waits) == (1, [])


async def test_lambda_transport_raises_the_runtime_error_on_function_error() -> None:
    client = _FakeLambda(function_error="Unhandled")
    with pytest.raises(RuntimeError, match="Task timed out"):
        await _send(client)


def test_lambda_client_never_re_sends_an_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    # An SDK retry or a read timeout below the function's would re-run a whole turn.
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    config = LambdaTransport.from_function_name("petbot-core")._client.meta.config  # type: ignore[attr-defined]
    assert config.retries["total_max_attempts"] == 1
    assert config.read_timeout > 900  # Lambda's maximum function timeout


async def test_lambda_transport_reports_waking_then_thinking_to_the_turn() -> None:
    # The frontend can only say "waking up" if the transport tells it the worker is down.
    phases: list[Phase] = []
    client = _FakeLambda(active=False)
    with observe(phases.append):
        result = await _send(client, ready_timeout=10)
    assert result.text == "ran"
    assert phases == [Phase.WAKING, Phase.THINKING]


async def test_lambda_transport_reports_nothing_for_a_ready_function() -> None:
    phases: list[Phase] = []
    with observe(phases.append):
        await _send(_FakeLambda())
    assert phases == []


# --- ClaimingProcess / DynamoClaims -------------------------------------------


class _AtomicClaims:
    """An in-memory ClaimStore: the first claim of an id wins."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.taken: set[str] = set()
        self._error = error

    async def claim(self, request_id: str) -> bool:
        if self._error is not None:
            raise self._error
        await asyncio.sleep(0)  # let a concurrent delivery interleave
        if request_id in self.taken:
            return False
        self.taken.add(request_id)
        return True


class _CountingProcess(Process):
    def __init__(self) -> None:
        self.calls = 0

    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        self.calls += 1
        return SkillResult.message("the answer")


def _ctx_for(request_id: str | None) -> SkillContext:
    return _ctx().model_copy(update={"request_id": request_id})


async def test_concurrent_deliveries_of_one_message_get_one_answer() -> None:
    # Two edge copies on the gateway both deliver the same Discord message at once.
    inner = _CountingProcess()
    process = ClaimingProcess(inner, _AtomicClaims())
    results = await asyncio.gather(
        process.respond(_command(), _ctx_for("discord:message:1")),
        process.respond(_command(), _ctx_for("discord:message:1")),
    )
    assert inner.calls == 1
    assert sorted(r.text or "" for r in results) == ["", "the answer"]
    assert any(r == SkillResult() for r in results)  # the loser renders as nothing


async def test_distinct_requests_and_unidentified_ones_are_all_answered() -> None:
    inner = _CountingProcess()
    process = ClaimingProcess(inner, _AtomicClaims())
    await process.respond(_command(), _ctx_for("discord:message:1"))
    await process.respond(_command(), _ctx_for("discord:message:2"))
    await process.respond(_command(), _ctx_for(None))  # e.g. a slash command
    await process.respond(_command(), _ctx_for(None))
    assert inner.calls == 4


async def test_a_failing_claim_store_still_answers() -> None:
    # A rare duplicate beats a dropped message.
    inner = _CountingProcess()
    process = ClaimingProcess(inner, _AtomicClaims(error=OSError("dynamodb down")))
    result = await process.respond(_command(), _ctx_for("discord:message:1"))
    assert result.text == "the answer"


class _FakeDynamo:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error

    def put_item(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return {}


async def test_dynamo_claim_is_a_conditional_create_with_a_ttl() -> None:
    client = _FakeDynamo()
    assert await DynamoClaims("petbot-core-claims", client, ttl_seconds=60).claim("m:1") is True
    call = client.calls[0]
    assert call["TableName"] == "petbot-core-claims"
    assert call["ConditionExpression"] == "attribute_not_exists(id)"
    assert call["Item"]["id"] == {"S": "m:1"}
    assert int(call["Item"]["expires_at"]["N"]) > 0


async def test_dynamo_claim_of_a_taken_id_is_refused() -> None:
    taken = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}}, "PutItem"
    )
    assert await DynamoClaims("t", _FakeDynamo(taken)).claim("m:1") is False


async def test_dynamo_claim_surfaces_other_errors() -> None:
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "PutItem")
    with pytest.raises(ClientError):
        await DynamoClaims("t", _FakeDynamo(denied)).claim("m:1")
