# AGENTS.md

High-signal guide for AI agents working in this repo. Pointers, not a textbook —
read [`docs/architecture.md`](docs/architecture.md) for the *why*.

## Invariants (do not violate)

1. **`petbot.core` imports no `discord` and no `petbot.frontends`.** Enforced by
   `lint-imports` and `tests/test_core_isolation.py`. The one-way rule is the
   whole point of the design.
2. **Skills are pure w.r.t. the platform.** They read `args`/`ctx`, return a
   `SkillResult`, and branch on `ctx.capabilities.*` — never on the platform name.
3. **Explicit content is gated on `ctx.capabilities.allows_explicit`** (the
   Discord adapter sets it from `channel.is_nsfw()`).
4. **Never block the event loop.** Offload `numexpr`/`yt-dlp`/any sync work with
   `asyncio.to_thread`.
5. **Tests + docs accompany every behavior change.** External APIs are mocked
   (fixtures + `FakeSession`); never hit them live.
6. **`ghost_talk` is intentionally removed** (cross-guild impersonation). Don't
   reintroduce it. Admin deletion (`/purge`) stays permission-gated.
7. **Logging is configured once, at the entrypoint.** Modules do
   `logger = logging.getLogger(__name__)` and never configure handlers/levels at
   import time; `configure_logging()` (called from `bootstrap.run`) is the only
   setup point. **Never log secrets/tokens** — log booru searches from the
   neutral `SearchRequest`, never the wire request. See
   [`docs/adr/0004-logging.md`](docs/adr/0004-logging.md).

## Where things live

- Neutral logic: `petbot/core/` (skills, registry, ports, booru capabilities).
- Discord adapter: `petbot/frontends/discord/` (bootstrap, context, render,
  voice, cogs). It's the only place `discord` is imported.
- Tests: `tests/` (+ `tests/fixtures/` for saved API responses).
- Config: `petbot/config.py` — the only reader of the environment.

## Commands

```bash
pip install -e ".[dev]"                 # setup
ruff check . && ruff format --check .   # lint + format
mypy                                    # strict typing
lint-imports                            # core/adapter boundary
pytest                                  # offline tests
op run --env-file=.env -- python -m petbot   # run (1Password); or `python -m petbot`
```

CI runs lint/format/mypy/lint-imports/pytest and needs **no secrets**.

## Adding things

Adding a skill or a frontend: follow [`docs/contributing.md`](docs/contributing.md).
The LLM layer is deferred and provider-agnostic — see
[`docs/adr/0002-deferred-llm.md`](docs/adr/0002-deferred-llm.md); don't add an
LLM SDK without that decision being made.
