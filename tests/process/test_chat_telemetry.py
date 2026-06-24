"""The chat process's telemetry: a metadata-only run-outcome record, and — when
instrumented — agent spans that never carry message content (``include_content=False``)."""

from __future__ import annotations

import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.test import TestModel

from petbot.domain import Platform, Recalled, SkillContext, TextInput, Unrecalled, User
from petbot.observability import hash_user_id
from petbot.platform import ToolRegistry
from petbot.process import ChatProcess

_SECRET = "SECRET_PROMPT_TEXT_protogen"


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="42", display_name="tester"),
        conversation_id="discord:1",
    )


async def test_run_outcome_is_logged_metadata_only(caplog: pytest.LogCaptureFixture) -> None:
    chat = ChatProcess(ToolRegistry([]), model=TestModel(call_tools=[]), id_salt="s")
    with caplog.at_level(logging.INFO, logger="petbot.process.chat"):
        await chat.respond(TextInput(text=_SECRET), _ctx())

    rec = next(r for r in caplog.records if r.getMessage() == "agent run")
    fields = rec.__dict__  # the extra={...} keys land here (dict[str, Any])
    assert fields["tool_count"] == 0 and fields["tools"] == []
    assert isinstance(fields["input_tokens"], int) and isinstance(fields["output_tokens"], int)
    assert fields["user"] == hash_user_id("42", "s")  # salted hash, not the raw id
    # Metadata only: neither the prompt text nor the raw user id is anywhere in the record.
    assert _SECRET not in str(fields)
    assert fields["user"] != "42"


async def test_run_outcome_records_reply_context(caplog: pytest.LogCaptureFixture) -> None:
    # The new observable failure mode: a reply whose prior context couldn't be read.
    chat = ChatProcess(ToolRegistry([]), model=TestModel(call_tools=[]), id_salt="s")
    with caplog.at_level(logging.INFO, logger="petbot.process.chat"):
        await chat.respond(TextInput(text="hi", history=Recalled(turns=())), _ctx())
        await chat.respond(TextInput(text="hi", history=Unrecalled()), _ctx())
    contexts = [r.__dict__["context"] for r in caplog.records if r.getMessage() == "agent run"]
    assert contexts == ["recalled", "unrecalled"]


async def test_instrumented_run_emits_spans_without_content() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instr = InstrumentationSettings(version=3, tracer_provider=provider, include_content=False)

    chat = ChatProcess(ToolRegistry([]), model=TestModel(call_tools=[]), instrumentation=instr)
    await chat.respond(TextInput(text=_SECRET), _ctx())

    spans = exporter.get_finished_spans()
    assert any(s.name.startswith("invoke_agent") for s in spans), "no agent-run span"
    dump = repr([dict(s.attributes or {}) for s in spans])
    assert _SECRET not in dump, "message content leaked into span attributes"
