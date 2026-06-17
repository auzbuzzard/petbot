# PetBot

A modern Discord bot that you **talk to**: @mention PetBot and it replies in
natural language, calling skills — image search (Derpibooru, e621), math, music —
as tools when the conversation calls for them. Built as **A3a**: a thin,
always-on **edge** that holds the Discord gateway and dispatches to skill
**workers**, so compute scales (and goes serverless) independently of the
connection.

This is the 2.1 release — the LLM/agent layer landing on the 2.0 neutral core.
The original 2018 bot (built on the long-removed `discord.py` 0.16 "async"
branch) is preserved at the git tag **`v0.1-legacy-2018`**.

## What it does

@mention PetBot and chat. The agent (pydantic-ai) decides when to call a tool:

| Tool | What it does |
| --- | --- |
| `math` | Evaluate an arithmetic expression (`numexpr`). |
| `derpi` | Search Derpibooru (comma-separated tags). |
| `e621` | Search e621 (space-separated tags, `_` within a tag). |
| `music` | Voice playback with a queue and skip-votes (its own worker). |

Booru results are restricted to the safe rating outside age-restricted (NSFW)
channels; inside a NSFW channel every rating is returned.

## Architecture

```
Discord ⇄ [ edge ]  --SkillCall(JSON)-->  [ brain worker ]  math · booru · chat(LLM)
          gateway      HTTP / Lambda        \--> [ music worker ] gateway + voice
```

The edge runs no skills; it holds a typed `Skills` client and calls
`await skills.chat(ChatArgs(message), ctx)`. The client serialises a `SkillCall`
to a worker, which re-validates the args and runs the skill. The chat skill's LLM
tools are its sibling skills (math/booru), called in-process. One uv workspace,
many `petbot.*` packages — see [`AGENTS.md`](AGENTS.md) and
[`docs/adr/0006-gateway-edge-microservice-skills.md`](docs/adr/0006-gateway-edge-microservice-skills.md).

The LLM is provider-agnostic (no vendor lock-in): Amazon Bedrock in prod, an
OpenAI-compatible endpoint (OpenRouter, with free models) in dev — chosen by
`CHAT_PROVIDER`.

## Quickstart

Requirements: **[uv](https://docs.astral.sh/uv/)** (it fetches Python 3.12 for
you) and, for voice, the **FFmpeg** system binary.

```bash
uv sync --all-extras --all-packages   # install every workspace member + dev tooling
cp .env.example .env                  # then fill in your secrets/references

# In one shell: a local brain worker (math + booru + chat) on :8000
python -m petbot.workers.brain
# In another: the edge (talks to the worker over HTTP by default)
python -m petbot.discord
```

@mention the bot in a server it's in and start chatting.

### Configuration

All configuration is read from the environment (see `.env.example` for the full
list). The edge needs `DISCORD_TOKEN` and the worker address (`TRANSPORT` +
`WORKER_URL`/`WORKER_LAMBDA`); the brain worker needs the chat model config
(`CHAT_*`) and optional booru creds. **1Password** is recommended (keep `op://`
references in `.env`, launch with `op run --env-file=.env -- …`); a plaintext
`.env` is the fallback and is gitignored.

The **Message Content** privileged intent **is** required for the edge (the
conversational entrypoint reads what you type).

## Development

```bash
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                           # strict type-check
uv run lint-imports                                   # package boundaries
uv run pytest                                         # tests (fully offline)
```

CI runs all of the above on every push and pull request. It needs **no
secrets** — every test is offline (mocked APIs, pydantic-ai `TestModel`, no
Discord login).
