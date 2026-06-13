"""Tests for the logging setup: JSON formatter, the non-error filter, and the
``configure_logging`` entrypoint.

These never touch the network and restore the root logger afterwards, so they
don't leak handlers into the rest of the suite. (``Settings`` log-field parsing
is covered in ``test_config.py``.)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from collections.abc import Iterator
from types import TracebackType

import pytest

from petbot.logging_setup import JSONFormatter, NonErrorFilter, configure_logging


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Snapshot the root logger and put it back after the test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def _record(
    *,
    msg: str = "hello %s",
    args: tuple[object, ...] = ("world",),
    level: int = logging.INFO,
    exc_info: tuple[type[BaseException], BaseException, TracebackType] | None = None,
) -> logging.LogRecord:
    return logging.LogRecord(
        name="petbot.test",
        level=level,
        pathname=__file__,
        lineno=10,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )


# --- JSONFormatter -----------------------------------------------------------


def test_json_formatter_emits_message_and_timestamp() -> None:
    record = _record()
    payload = json.loads(JSONFormatter().format(record))
    assert payload["message"] == "hello world"
    assert "timestamp" in payload


def test_json_formatter_maps_fmt_keys_and_merges_extras() -> None:
    formatter = JSONFormatter(fmt_keys={"level": "levelname", "logger": "name"})
    record = _record()
    # This is exactly how Logger.makeRecord attaches an ``extra={...}`` field.
    record.__dict__["request_id"] = "abc-123"
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "petbot.test"
    assert payload["request_id"] == "abc-123"


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        assert exc.__traceback__ is not None
        record = _record(level=logging.ERROR, exc_info=(type(exc), exc, exc.__traceback__))
    payload = json.loads(JSONFormatter().format(record))
    assert "ValueError: boom" in payload["exc_info"]


# --- NonErrorFilter ----------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "passes"),
    [
        (logging.DEBUG, True),
        (logging.INFO, True),
        (logging.WARNING, False),
        (logging.ERROR, False),
    ],
)
def test_non_error_filter(level: int, passes: bool) -> None:
    assert NonErrorFilter().filter(_record(level=level)) is passes


# --- configure_logging -------------------------------------------------------


def test_configure_logging_plain(restore_logging: None) -> None:
    configure_logging(level="DEBUG", fmt="plain")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)


def test_configure_logging_json_is_queued(restore_logging: None) -> None:
    configure_logging(level="INFO", fmt="json")
    handler = logging.getHandlerByName("queue_handler")
    assert isinstance(handler, logging.handlers.QueueHandler)
    # 3.12's dictConfig wires (and configure_logging starts) the background listener.
    assert getattr(handler, "listener", None) is not None


def test_configure_logging_rejects_unknown_format(restore_logging: None) -> None:
    with pytest.raises(ValueError, match="Unknown log format"):
        configure_logging(fmt="xml")


def test_configure_logging_rejects_unknown_level(restore_logging: None) -> None:
    with pytest.raises(ValueError, match="Unknown log level"):
        configure_logging(level="LOUD", fmt="plain")
