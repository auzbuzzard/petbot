# AGENTS.md

High-signal guide for agents working in this repo. Pointers, not a textbook —
read [`docs/architecture.md`](docs/architecture.md) for the *why*.

## Architecture

A thin, always-on Discord **frontend** holds the gateway and runs no skills; it
dispatches every request to a **compute service** that runs the process. One
installable package (`petbot`) under `src/`, with install-extras slicing
dependencies per process:

Organised by **concept** (`src/`), deployed by **service** (`deploy/` + `petbot.services`):

| Module | Role |
|---|---|
| `petbot.domain` | Kernel: frozen models (`SkillResult`, `SkillContext`, `EmbedSpec`, the `Input` sum type `TextInput \| CommandInput` — `TextInput` carries reply-chain `history: Recalled \| Unrecalled` — the turns PetBot recalled, or a marker that it *couldn't*), the `Process` verb + the `Skill[ArgsT]` tool ABC, ports (`VoicePort`, `StylePort`, `Notifier`), and `SkillError`. Imports nothing else first-party. |
| `petbot.process` | **The core.** The `Process` impls: `ChatProcess` (the LLM brain — maps `history` to `message_history` and **reactively compacts** it on a provider length-rejection, via a DI-selected `SlidingWindow`/`Summarizer`), `CommandProcess`, the `RouterProcess` (the one exhaustive `match` on input type), and the persona voice (`Stylist` / `PassthroughStyle`, a `StylePort`). |
| `petbot.skills.{math,booru,music}` | One **tool** each (a `Skill[ArgsT]`); the process calls them through the `ToolRegistry`. Tools *raise* `SkillError` for expected failures. |
| `petbot.types` | The typed surface a frontend imports without a skill: per-skill `*Args` models + the `Command` / `CATALOG`. |
| `petbot.platform` | Plumbing: `ToolRegistry`, `serve`, `ProcessClient`, the `Dispatch` envelope + transports (`HttpTransport`, `LambdaTransport`). |
| `petbot.frontends.{discord}` | Driving adapters: map a platform event to an `Input`, dispatch via a `ProcessClient`, render the `SkillResult`. |
| `petbot.services.{core,music}` | Composition roots (deploy-by-service): wire process + skills + platform and `serve` it. core = chat + command over math/booru; music = the voice service. |

The calling pattern: a frontend builds a neutral `Input` (`TextInput` for `@mention`,
`CommandInput` for slash) + a `SkillContext` and calls `await process.respond(inp, ctx)`
on its `ProcessClient` (over a transport). On the compute side `serve` decodes the
`Dispatch`, the `RouterProcess` picks `ChatProcess`/`CommandProcess` by the input *type*
(the one exhaustive `match`), and the process calls its tools through the `ToolRegistry`,
which validates raw values against each skill's `args_model`. mypy `--strict` checks every
call across modules.

## Install extras

`pip install petbot[discord]` (discord.py, httpx), `petbot[compute-core]`
(pydantic-ai, numexpr), `petbot[compute-music]` (yt-dlp, voice), `petbot[lambda]`
(boto3), `petbot[dev]` (everything + tooling). The module boundaries are enforced
statically by `lint-imports`, not by packaging.

## Invariants (do not violate)

1. **`petbot.domain` imports nothing else first-party and no `discord`/`httpx`.**
   A frontend never imports a skill or the process core; the process core never imports
   a concrete skill. Enforced by `lint-imports`.
2. **Skills are pure tools.** They read typed `args` + `ctx`, return a `SkillResult` (or
   **raise** a `SkillError` for an expected failure), and branch on `ctx` flags — never on
   the platform name. The process output boundary catches a `SkillError` and voices it once
   through the `StylePort`; there is no error channel on `SkillResult`.
3. **Explicit content is gated on `ctx.allows_explicit`** (the frontend sets it from
   `channel.is_nsfw()`).
4. **`SkillContext` is pure serialisable data** — no live ports, no presentation flags. A
   voice-needing skill gets its port from an injected `VoiceProvider` compute-side.
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
(`class ProcessClient(Process)`, `class HttpTransport(Transport)`) so mypy verifies
conformance at the definition. Structural (no inheritance) is reserved for foreign
types and test fakes.

## Comments

Comments are **time-invariant**: they describe the code as it is, not how it got there. No
change history ("now", "previously", "was X", "an earlier draft"), no narrating what a diff
replaced — git holds that. Explain *why* when it isn't obvious from the code; don't restate
*what*. Keep them short. (Commit messages, not comments, are where change rationale lives.)

## Adding a skill

1. Add the `*Args` model in `petbot.types.args` and a `Command` entry in
   `petbot.types.catalog` (`CATALOG`).
2. Create `petbot/skills/<name>/` with a `Skill[<Args>]` subclass; register an entry
   point under `petbot.skills` (or build it explicitly in a service if it needs DI).
3. It's hosted wherever its extra is installed; the slash surface and the chat agent both
   pick it up from `CATALOG` for free.

## Commands

```bash
uv sync --all-extras                             # setup
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                      # strict typing
uv run lint-imports                              # module boundaries
uv run pytest                                    # offline tests

python -m petbot.services.core                   # local core compute service (:8000)
python -m petbot.frontends.discord               # the Discord frontend (talks to it)
```

CI runs lint/format/mypy/lint-imports/pytest and needs **no secrets**.
