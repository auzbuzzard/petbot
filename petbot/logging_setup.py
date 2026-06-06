"""Logging setup — configured **once**, at the entrypoint, never at import time.

The whole app follows the modern (3.12) logging shape popularised by mCoding's
"modern logging" talk: every module grabs a ``logging.getLogger(__name__)`` and
just emits; the *only* place that wires handlers/levels is
:func:`configure_logging`, called by the Discord bootstrap before the bot starts.

The configuration itself lives in JSON (loaded via :mod:`importlib.resources` and
:func:`logging.config.dictConfig`), with two profiles shipped as package data:

* ``plain`` — one human-readable line per record to *stderr* (the dev default);
* ``json`` — structured JSON-lines, routed through a :class:`QueueHandler` so the
  actual I/O happens on a background :class:`QueueListener` thread and never
  blocks the asyncio event loop (the prod default).

Nothing here reads the environment: the level and profile are passed in by the
caller, which got them from :class:`~petbot.config.Settings` (the one env reader).
"""

from __future__ import annotations

import atexit
import datetime as dt
import json
import logging
import logging.config
from importlib import resources
from logging.handlers import QueueHandler, QueueListener
from typing import Any, Final, override

__all__ = ["JSONFormatter", "NonErrorFilter", "configure_logging"]

#: Profile name -> packaged ``dictConfig`` JSON file (under ``logging_configs/``).
_CONFIG_FILES: Final[dict[str, str]] = {
    "plain": "plain.json",
    "json": "structured.json",
}

#: Attributes already present on every :class:`logging.LogRecord`. Anything *not*
#: in here that a caller attached via ``extra={...}`` is treated as structured
#: context and merged into the JSON output by :class:`JSONFormatter`.
_BUILTIN_RECORD_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)

#: The currently-running queue listener, if any. Tracked so a reconfigure (e.g.
#: in tests) tears the old background thread down before standing a new one up,
#: and so a single :mod:`atexit` hook can stop whatever is current.
_active_listener: QueueListener | None = None
_atexit_registered = False


class JSONFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single JSON-lines object.

    ``message`` and ``timestamp`` (ISO-8601 UTC) are always emitted; ``fmt_keys``
    maps any other output key to a record attribute (e.g. ``{"level":
    "levelname"}``). Anything attached via ``extra=`` rides along as structured
    context, and ``exc_info``/``stack_info`` are folded in when present.
    """

    def __init__(self, *, fmt_keys: dict[str, str] | None = None) -> None:
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}

    @override
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(self._prepare(record), default=str)

    def _prepare(self, record: logging.LogRecord) -> dict[str, Any]:
        always: dict[str, Any] = {
            "message": record.getMessage(),
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
        }
        if record.exc_info is not None:
            always["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info is not None:
            always["stack_info"] = self.formatStack(record.stack_info)

        # Pull "always" fields out by name where the caller asked for them, else
        # read the attribute straight off the record.
        message: dict[str, Any] = {
            key: value if (value := always.pop(src, None)) is not None else getattr(record, src)
            for key, src in self.fmt_keys.items()
        }
        message.update(always)

        for key, value in record.__dict__.items():
            if key not in _BUILTIN_RECORD_ATTRS:
                message[key] = value
        return message


class NonErrorFilter(logging.Filter):
    """Pass only DEBUG/INFO records — used to split stdout (info) from stderr."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO


def configure_logging(*, level: str | int = "INFO", fmt: str = "plain") -> None:
    """Configure logging for the whole process. Call this **once**, at start-up.

    ``fmt`` selects a packaged profile (``"plain"`` or ``"json"``); ``level`` sets
    the root logger level (a name like ``"DEBUG"`` or a numeric level). Starts the
    background queue listener when the chosen profile uses one, and registers its
    shutdown via :mod:`atexit`. Safe to call again (tests do): the previous queue
    listener is stopped first.
    """
    global _atexit_registered

    _stop_active_listener()
    config = _load_config(fmt)
    config["root"]["level"] = _resolve_level(level)
    logging.config.dictConfig(config)
    if _start_queue_listener() is not None and not _atexit_registered:
        # One hook, stopping whatever listener is current — re-registering per
        # listener would fire stale ``stop()`` calls on already-stopped ones.
        atexit.register(_stop_active_listener)
        _atexit_registered = True


def _stop_active_listener() -> None:
    global _active_listener
    if _active_listener is not None:
        _active_listener.stop()
        _active_listener = None


def _load_config(fmt: str) -> dict[str, Any]:
    try:
        filename = _CONFIG_FILES[fmt]
    except KeyError:
        raise ValueError(
            f"Unknown log format {fmt!r}; expected one of {sorted(_CONFIG_FILES)}."
        ) from None
    text = (
        resources.files(__package__)
        .joinpath("logging_configs", filename)
        .read_text(encoding="utf-8")
    )
    config: dict[str, Any] = json.loads(text)
    return config


def _resolve_level(level: str | int) -> str | int:
    if isinstance(level, int):
        return level
    name = level.upper()
    if name not in logging.getLevelNamesMapping():
        raise ValueError(f"Unknown log level {level!r}.")
    return name


def _start_queue_listener() -> QueueListener | None:
    """Start the listener behind ``queue_handler`` (if the profile defines one).

    3.12's ``dictConfig`` builds the :class:`QueueListener` and attaches it to the
    handler as ``.listener``; it must be explicitly started/stopped. The started
    listener is recorded in ``_active_listener`` for shutdown.
    """
    global _active_listener
    handler = logging.getHandlerByName("queue_handler")
    if not isinstance(handler, QueueHandler):
        return None
    listener: QueueListener | None = getattr(handler, "listener", None)
    if listener is None:
        return None
    listener.start()
    _active_listener = listener
    return listener
