# AGENTS.md

High-signal guide for AI agents working in this repo. Pointers, not a textbook —
read [`docs/adr/0006-gateway-edge-microservice-skills.md`](docs/adr/0006-gateway-edge-microservice-skills.md)
for the *why*.

## Architecture (A3a)

A thin, always-on Discord **edge** holds the gateway and runs **no** skills; it
dispatches every request to a **worker** that does. One uv workspace, many
independently-installable packages under the `petbot.*` namespace (PEP 420):

| Package | Import | Role |
|---|---|---|
| `domain/` | `petbot.domain` | Shared kernel: frozen pydantic models (`SkillResult`, `SkillContext`, …), the generic `Skill[ArgsT]` ABC, ports (`VoicePort`, `VoiceProvider`), and the wire primitives (`SkillCall`, `Transport`). Pure data; depends on nothing first-party. |
| `types/` | `petbot.types` | The typed surface the edge imports *without* skills: per-skill `*Args` models + the `Skills` client Protocol. |
| `platform/` | `petbot.platform` | `Worker` (runs a dispatched call), `RemoteSkills`/`LocalSkills` (the `Skills` impls), `HttpTransport`/`LambdaTransport`. |
| `skills/{math,booru,music,chat}/` | `petbot.skills.*` | One skill each. `chat` is the pydantic-ai agent whose tools are its sibling skills. |
| `frontends/discord/` | `petbot.discord` | The edge: `@mention` → `skills.chat(...)` → render. |
| `workers/{brain,music}/` | `petbot.workers.*` | Deployable bundles: brain = math+booru+chat (Lambda/HTTP); music = gateway+voice host. |

The calling pattern: the edge holds a `Skills` client (`RemoteSkills` over a
`Transport`) and calls `await skills.chat(ChatArgs(...), ctx)`. The client
serialises a `SkillCall`; the worker re-validates the args against the skill's
`args_model` and runs it. mypy `--strict` checks every call across packages.

## Invariants (do not violate)

1. **`petbot.domain` imports nothing first-party and no `discord`/`httpx`.** The
   edge never imports a skill. Enforced by `lint-imports` (see `[tool.importlinter]`).
2. **Skills are pure w.r.t. the platform.** They read typed `args` + `ctx`, return
   a `SkillResult`, and branch on `ctx` flags — never on the platform name.
3. **Explicit content is gated on `ctx.allows_explicit`** (the edge sets it from
   `channel.is_nsfw()`).
4. **`SkillContext` is pure serialisable data** — no live ports ride on it. A
   voice-needing skill gets its port from an injected `VoiceProvider` worker-side.
5. **Never block the event loop.** Offload `numexpr`/`yt-dlp`/sync work with
   `asyncio.to_thread`.
6. **Tests + docs accompany every behaviour change.** External APIs are mocked
   (`respx`, fixtures); the LLM is tested with pydantic-ai's `TestModel`. Never hit
   them live.
7. **Never log secrets/tokens** — log booru searches from the neutral
   `SearchRequest`, never the wire request.

## Adding a skill

1. Add its `*Args` model + a `Skills` method in `petbot.types`.
2. Add a `RemoteSkills`/`LocalSkills` method (one line each) in `petbot.platform`.
3. Create `skills/<name>/` with a `Skill[<Args>]` subclass; register an entry
   point under `petbot.skills` (or build it explicitly if it needs DI).
4. Host it in the relevant worker; expose it as a chat tool if conversational.

## Commands

```bash
uv sync --all-extras --all-packages              # setup (uv workspace)
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                      # strict typing
uv run lint-imports                              # package boundaries
uv run pytest                                    # offline tests

python -m petbot.workers.brain                   # run a local brain worker (:8000)
python -m petbot.discord                         # run the edge (talks to the worker)
```

CI runs lint/format/mypy/lint-imports/pytest and needs **no secrets**.

## Editor note

Pylance can't follow editable namespace installs; `pyrightconfig.json` points it
at each member's source root. CI's typing authority is `mypy --strict`.
