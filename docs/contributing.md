# Contributing

## Working agreement

No behavior change merges without **tests and green CI**. A new skill ships with
its tests; a bug fix ships with a regression test that fails before the fix; a
refactor keeps existing tests green. Update the docs in the same change that
alters the behavior they describe.

The four gates (all required to merge, all runnable locally):

```bash
ruff check . && ruff format --check .   # lint + format
mypy                                    # strict typing
lint-imports                            # core/adapter boundary
pytest                                  # offline tests
```

`pre-commit install` runs lint/type on every commit.

## Adding a skill

1. Create `petbot/core/skills/<name>_skill.py` with a `Skill` subclass:
   - class vars `name`, `description`, `input_schema` (JSON Schema), and
     `requires` (e.g. `frozenset({"voice"})`) if it needs a port;
   - `async def run(self, args, ctx) -> SkillResult`.
2. Keep it **pure**: read from `args`/`ctx`, return a `SkillResult`, never import
   `discord`. Gate explicit content on `ctx.capabilities.allows_explicit`.
   Offload blocking work with `asyncio.to_thread`.
3. Register it in `petbot/frontends/discord/bootstrap.py` and add a thin cog in
   `petbot/frontends/discord/cogs/` that builds a context, calls the skill, and
   renders via `render.respond`.
4. Add tests in `tests/` using `make_context(...)` and (for network) the
   `FakeSession`/fixtures. Never hit a live API.

## Adding a frontend (adapter)

Create `petbot/frontends/<platform>/`. Translate the platform's events into a
`SkillContext` (set the `Capabilities` flags honestly), call skills via a
`SkillRegistry`, implement any ports the skills need (e.g. a `VoicePort`), and
render `SkillResult`/`EmbedSpec` natively. Do **not** import the new frontend
from `petbot.core`.

## Tests & fixtures

- Core logic is tested directly (no gateway). See `tests/test_*_skill.py`.
- External APIs are mocked with saved JSON fixtures in `tests/fixtures/` plus
  the `FakeSession` in `tests/conftest.py`. Add new fixtures (including
  error/empty cases) rather than calling the real site.
- The Discord gateway bootstrap is smoke-tested manually against a dev guild,
  not in CI.
