# ADR 0004: Modern, 3.12-native logging

- Status: Accepted
- Date: 2026-06-02

## Context

The 2.0 revival shipped with no real logging story — a lone
`logging.basicConfig(level=INFO)` in `bootstrap.run` and otherwise silence.
Issue #25 asks for idiomatic Python `logging` across the codebase, deliberately
sequenced *after* the booru rewrite (#24) so it wires into the final structure.

We want the modern shape: per-module loggers, configuration in exactly one
place, structured output we can ship to a log aggregator, and — because PetBot
runs on a single asyncio event loop (AGENTS invariant #4) — logging I/O that
never blocks that loop. The reference is mCoding's "modern logging" talk
([video 135](https://youtu.be/9L77QExPmI0)).

## Decision

- **Per-module loggers, no import-time config.** Every module does
  `logger = logging.getLogger(__name__)` and just emits. The *only* place that
  configures handlers/levels is `configure_logging()` in
  [`petbot/logging_setup.py`](../../petbot/logging_setup.py), called once from
  `bootstrap.run` before the bot starts. `bot.run(..., log_handler=None)` stops
  discord.py installing its own handler, so `discord.*` loggers propagate into
  ours.
- **`dictConfig` from JSON.** Configuration is data, not code: JSON files under
  `petbot/logging_configs/` loaded via `importlib.resources` and
  `logging.config.dictConfig`. Two profiles ship as package data:
  - `plain` — one human-readable line per record → stderr (dev default).
  - `structured` (`json`) — JSON-lines, routed through a `QueueHandler` so a
    background `QueueListener` does the I/O; INFO/DEBUG → stdout, WARNING+ →
    stderr (prod default).
- **Custom `JSONFormatter` + `NonErrorFilter`** live in `logging_setup.py`,
  using `typing.override`, `datetime.UTC`, and `logging.getHandlerByName` —
  3.12-only APIs. This is the concrete reason the project pins
  `requires-python = ">=3.12"`.
- **Env-driven, via `config.py` only.** `LOG_LEVEL` (default `INFO`) and
  `LOG_FORMAT` (`plain`|`json`, else derived from `ENV`) are parsed by
  `Settings.from_env`, honoring the "`config.py` is the only env reader"
  convention, then passed into `configure_logging`.
- **Never log secrets.** Booru activity is logged from the neutral
  `SearchRequest` (tags/flags), never the wire request, which can carry an
  api-key/User-Agent. Levels: DEBUG for request/parse internals, INFO for
  lifecycle, WARNING/ERROR for failures.
- **Log errors once, at the handler — never log-and-raise.** A raised exception
  *is* the error report; logging it at the `raise` site and again where it's
  caught produces duplicate, confusing output. So the low-level code (e.g. the
  booru `engine`) only raises; the boundary that *handles* the exception (the
  skill's `try/except`, which turns it into a `SkillResult`) is the single place
  that logs it, choosing the level by severity and attaching a traceback
  (`exc_info=True` / `logger.exception`) only when one aids debugging. An
  expected, user-surfaced failure (a site rejecting a query) is a DEBUG
  breadcrumb with no traceback; an unexpected network/parse failure is a WARNING
  with the traceback. Code that merely re-raises logs nothing and lets it
  propagate.

## Consequences

- A non-blocking queue keeps log I/O off the event loop; the listener is started
  in `configure_logging` and stopped via `atexit`.
- Prod emits machine-parseable JSON-lines ready for any aggregator; dev stays
  readable.
- The project is now firmly 3.12+ (already reflected in `pyproject.toml`); the
  README requirement is bumped to match.
- Adding a third profile (e.g. a rotating file) is a new JSON file plus a key in
  `_CONFIG_FILES` — no code in callers changes.
