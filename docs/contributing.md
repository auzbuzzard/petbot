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

A Claude code review of a pull request runs on demand: add the `claude-review` label
(`claude-code-review.yml`). Remove and re-add it to review again after new commits.

## Trying a change against the real model

The offline tests can't tell whether a prompt reads well or a tool answers the question.
Before a persona, prompt or tool change merges, run it through the real model with the
chat harness. It takes production's path with no Discord and no server: each message of a
scripted conversation is encoded as a dispatch and handed to `serve`, which runs this
checkout's core process in-process, so an unexpected error gets production's reply (and a
logged traceback) and the conversation goes on. It prints each reply as the Discord
frontend would post it, after the agent's tool calls; `-v` adds what each call returned to
the model, and a call the model got wrong or the turn's budget cut off is marked.

```bash
python -m petbot.services.core.chat conversations/leetcode-daily.json -v
python -m petbot.services.core.chat --say "what's the weather in Paris?" --as Ann
```

It reads the same settings as the core service (`CHAT_LLM__*`, `TAVILY_API_KEY`, the booru
keys, `OBS_*`; see `.env.example`) from the environment or `.env`, and the frontend's
`HISTORY_MAX_TURNS`. A conversation file lists the place (`server`, `channel`, `nsfw`) and
the messages in order. Each goes to PetBot unless `"to_bot": false`; the messages form one
reply chain from the last `"fresh": true` one (a new @mention) on, and PetBot's history is
that chain as the frontend reads it back. Each turn's budget is the core Lambda's timeout
(`--timeout`, default Terraform's 120 s) less the handler's reserve, as in production. Add a
file under `conversations/` for any case worth re-running; use placeholder names, never a
real server's messages.

### Against a deployed dev core

Some answers need the deployed function: whether a site serves requests from AWS's
addresses, whether the Lambda's IAM and packaging hold. Deploy the branch's core to dev
(the engine alone: no Discord bot, no edge). CI does it for every pull request from this
repository: `deploy.yml` deploys the pull request to `petbot-dev-core`, then its `test` job
runs `tests/live` against it and that is the pull request's check:

- every skill through the slash path, checked for the facts its tool returns;
- every file in `conversations/` through chat, checked that each message gets a reply.

The transcripts are in the run's summary; each turn's tool calls are in the function's log
group (`/aws/lambda/petbot-dev-core`). A case worth keeping is a new conversation file or a
new skill case in `tests/live`. Pull requests from forks and Dependabot get no AWS access and
skip it. A run outside a pull request: `gh workflow run deploy.yml --ref <branch> -f
environment=dev`. Dev is one slot: the last deploy wins. See
[ADR 0014](adr/0014-dev-core-environment.md) and `deploy/terraform/README.md`.

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
