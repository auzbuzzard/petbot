# Contributing

## Working agreement

No behaviour change merges without **tests and green CI**. A new skill ships with
its tests; a bug fix ships with a regression test that fails before the fix; a
refactor keeps existing tests green. Update the docs in the same change.

The four gates (all required to merge, all runnable locally):

```bash
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                           # strict typing
uv run lint-imports                                   # package boundaries
uv run pytest                                         # offline tests
```

## Adding a skill

The full recipe is in [`AGENTS.md`](../AGENTS.md). In short:

1. Add the skill's `*Args` model in `petbot.types.args` and a `Command` entry in
   `petbot.types.catalog` (`CATALOG`).
2. Create `petbot/skills/<name>/` with a `Skill[<Args>]` subclass (typed `args_model`,
   `async def run(self, args, ctx) -> SkillResult`). Keep it **pure**: read
   `args`/`ctx`, return a `SkillResult` (or **raise** a `SkillError` for an expected
   failure), never import `discord`. Gate explicit content on `ctx.allows_explicit`;
   offload blocking work with `asyncio.to_thread`. Register an entry point under
   `petbot.skills` (or build it explicitly in a service if it needs DI, like `music`).
3. It's hosted wherever its extra is installed (the core service hosts the stateless
   skills); the slash surface and the chat agent both pick it up from `CATALOG` for
   free — no per-skill wiring in either.
4. Add tests under `tests/`. Mock HTTP with `respx` + saved fixtures; drive the LLM
   with pydantic-ai's `TestModel`. Never hit a live API or LLM.

## Adding a frontend

Add a `petbot.frontends.<platform>` module. Map the platform's events onto a neutral
`Input` (`TextInput`/`CommandInput`) + `SkillContext`, hold a `ProcessClient` (a
`Process` over a `Transport`), and render `SkillResult`/`EmbedSpec` natively. Do **not**
import a skill or the process core (`lint-imports` enforces this).

## Tests & fixtures

- Skills are tested directly (no gateway), under `tests/`.
- External APIs are mocked at the transport layer with `respx`, replaying saved
  JSON fixtures (`tests/skills/booru/fixtures/`). Add error/empty fixtures rather
  than calling the real site.
- The Discord gateway (the frontend, the music service) is smoke-tested manually
  against a dev guild, not in CI.
