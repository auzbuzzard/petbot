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

1. Add the skill's `*Args` model and a `Skills` Protocol method in
   `types/petbot/types/`.
2. Add the one-line `RemoteSkills` + `LocalSkills` methods in
   `platform/petbot/platform/skills.py`.
3. Create `skills/<name>/` with a `Skill[<Args>]` subclass (typed `args_model`,
   `async def run(self, args, ctx) -> SkillResult`). Keep it **pure**: read
   `args`/`ctx`, return a `SkillResult`, never import `discord`. Gate explicit
   content on `ctx.allows_explicit`; offload blocking work with
   `asyncio.to_thread`. Register an entry point under `petbot.skills` (or build it
   explicitly if it needs DI, like `music`/`chat`).
4. Host it in the relevant worker (`workers/brain` or `workers/music`); expose it
   as a `@agent.tool` in `skills/chat` if it should be conversational.
5. Add tests in `<package>/tests/`. Mock HTTP with `respx` + saved fixtures;
   drive the LLM with pydantic-ai's `TestModel`. Never hit a live API or LLM.

## Adding a frontend

Create `frontends/<platform>/` as a new `petbot.<platform>` package. Map the
platform's events onto a neutral `SkillContext`, hold a typed `Skills` client
(`RemoteSkills` over a `Transport`), and render `SkillResult`/`EmbedSpec`
natively. Do **not** import a skill (`lint-imports` enforces this).

## Tests & fixtures

- Skills are tested directly (no gateway), per package under `<pkg>/tests/`.
- External APIs are mocked at the transport layer with `respx`, replaying saved
  JSON fixtures (`skills/booru/tests/fixtures/`). Add error/empty fixtures rather
  than calling the real site.
- The Discord gateway (edge, music worker) is smoke-tested manually against a dev
  guild, not in CI.
