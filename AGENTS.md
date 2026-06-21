# AGENTS.md

High-signal guide for agents working in this repo. Pointers, not a textbook —
read [`docs/architecture.md`](docs/architecture.md) for the *why*.

## Architecture

A thin, always-on Discord **edge** holds the gateway and runs no skills; it
dispatches every request to a **worker** that does. One installable package
(`petbot`) under `src/`, with install-extras slicing dependencies per process:

| Module | Role |
|---|---|
| `petbot.domain` | Kernel: frozen pydantic models (`SkillResult`, `SkillContext`, `EmbedSpec`), the generic `Skill[ArgsT]` ABC, ports (`VoicePort`, `VoiceProvider`), and the dispatch primitives (`SkillCall`, `Transport`). Depends on nothing else first-party. |
| `petbot.types` | The typed surface the edge imports without skills: per-skill `*Args` models + the `Skills` client Protocol. |
| `petbot.platform` | `Worker` (runs a dispatched call), `SkillsClient` (the one `Skills` impl), and the transports (`LocalTransport`, `HttpTransport`, `LambdaTransport`). |
| `petbot.skills.{math,booru,music,chat}` | One skill each. `chat` is a pydantic-ai agent whose tools are its sibling skills; it also exports `LLMStyleProvider` (a `StyleProvider` port), the small LLM that restyles a result in PetBot's voice for the LLM-free slash path. |
| `petbot.edge` | The edge: `@mention` → `skills.chat(...)` → render. |
| `petbot.workers.{core,music}` | Deployable bundles: core = math+booru+chat (Lambda/HTTP); music = gateway + voice host. |

The calling pattern: the edge holds a `Skills` client — `SkillsClient(transport)`
— and calls `await skills.chat(ChatArgs(...), ctx)`. `SkillCall` carries the
*typed* args (no pre-serialisation); the transport delivers it (a local transport
in-process with no JSON, a remote transport serialising at the boundary), and the
worker validates the args against the skill's `args_model` and runs it. mypy
`--strict` checks every call across modules.

## Install extras

`pip install petbot[edge]` (discord.py, httpx), `petbot[worker-core]`
(pydantic-ai, numexpr), `petbot[worker-music]` (yt-dlp, voice), `petbot[lambda]`
(boto3), `petbot[dev]` (everything + tooling). The module boundaries are enforced
statically by `lint-imports`, not by packaging.

## Invariants (do not violate)

1. **`petbot.domain` imports nothing else first-party and no `discord`/`httpx`.**
   The edge never imports a skill. Enforced by `lint-imports`.
2. **Skills are pure w.r.t. the platform.** They read typed `args` + `ctx`, return
   a `SkillResult`, and branch on `ctx` flags — never on the platform name.
3. **Explicit content is gated on `ctx.allows_explicit`** (the edge sets it from
   `channel.is_nsfw()`).
4. **`SkillContext` is pure serialisable data** — no live ports on it. A
   voice-needing skill gets its port from an injected `VoiceProvider` worker-side.
5. **Never block the event loop.** Offload `numexpr`/`yt-dlp`/sync work with
   `asyncio.to_thread`.
6. **Logging is configured once, at each entrypoint.** Modules do
   `logger = logging.getLogger(__name__)` and never configure at import time;
   `configure_logging` (in `petbot.logging`) is the only setup point, fed by
   `LOG_LEVEL`. Never log secrets/tokens.
7. **Tests + docs accompany every behaviour change.** External APIs are mocked
   (`respx`, fixtures); the LLM is tested with pydantic-ai's `TestModel`.

## Typing convention

First-party classes that exist to implement a Protocol **explicitly subclass** it
(`class SkillsClient(Skills)`, `class HttpTransport(Transport)`) so mypy verifies
conformance at the definition. Structural (no inheritance) is reserved for foreign
types and test fakes.

## Adding a skill

1. Add the `*Args` model + a `Skills` method in `petbot.types`.
2. Add the one-line `SkillsClient` method in `petbot.platform.client`.
3. Create `petbot/skills/<name>/` with a `Skill[<Args>]` subclass; register an
   entry point under `petbot.skills` (or build it explicitly if it needs DI).
4. Host it in the relevant worker; expose it as a chat tool if conversational.

## Commands

```bash
uv sync --all-extras                             # setup
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                      # strict typing
uv run lint-imports                              # module boundaries
uv run pytest                                    # offline tests

python -m petbot.workers.core                    # local core worker (:8000)
python -m petbot.edge                            # the edge (talks to the worker)
```

CI runs lint/format/mypy/lint-imports/pytest and needs **no secrets**.
