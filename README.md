# PetBot

A Discord bot that you **talk to**: @mention PetBot and it replies in natural
language, calling skills — image search (Derpibooru, e621), math, music — as
tools when the conversation calls for them. The architecture separates a thin,
always-on **frontend** (it holds the Discord connection) from **compute services**
that run the process and its skills, so compute scales — and can go serverless —
independently of the connection.

The original 2018 bot (built on the long-removed `discord.py` 0.16 "async"
branch) is preserved at the git tag **`v0.1-legacy-2018`**.

## What it does

@mention PetBot and chat. The agent (pydantic-ai) decides when to call a tool:

| Tool | What it does |
| --- | --- |
| `math` | Evaluate an arithmetic expression (`numexpr`). |
| `derpi` | Search Derpibooru (comma-separated tags). |
| `e621` | Search e621 (space-separated tags, `_` within a tag). |
| `music` | Voice playback with a queue and skip-votes (its own service). |

Booru results are restricted to the safe rating outside age-restricted (NSFW)
channels; inside a NSFW channel every rating is returned.

## Architecture

```
Discord ⇄ [ frontend ]  --Input(JSON)-->  [ core service ]  chat(LLM) · math · booru
            gateway        HTTP / Lambda      \--> [ music service ]  gateway + voice
```

The frontend runs no skills and no process logic: it maps an @mention to a neutral
`TextInput` and each slash command to a `CommandInput`, then dispatches via a
`ProcessClient` over a transport (`HttpTransport` / `LambdaTransport`). The compute
service decodes it; a `RouterProcess` picks — by input type, the one place anything
branches — the **chat process** (the pydantic-ai brain) or the **command process**,
and tools are called in-process through a `ToolRegistry`. The chat agent's tools are
the very skills the slash commands expose, both derived from one `CATALOG`. See
[`AGENTS.md`](AGENTS.md) and the ADRs under [`docs/adr/`](docs/adr/).

One installable package (`petbot`); each process installs only the extra it
needs, so the frontend never pulls `pydantic-ai` and a compute service never pulls
`discord.py`. The LLM is provider-agnostic (Amazon Bedrock, or an
OpenAI-compatible endpoint such as OpenRouter), chosen by `CHAT_LLM__KIND`.

## Quickstart

Requirements: **[uv](https://docs.astral.sh/uv/)** (it fetches Python 3.12) and,
for voice, the **FFmpeg** system binary.

```bash
uv sync --all-extras                  # install petbot + every extra + dev tooling
cp .env.example .env                  # then fill in your secrets/references

# One shell: the local core compute service (math + booru + chat) on :8000
python -m petbot.services.core
# Another: the Discord frontend (talks to the service over HTTP by default)
python -m petbot.frontends.discord
```

@mention the bot in a server it's in and start chatting.

### Configuration

All configuration is read from the environment (see `.env.example`). The frontend
needs `DISCORD_TOKEN` and the compute service address (`SERVICE__KIND` +
`SERVICE__URL`/`SERVICE__FUNCTION_NAME`); the core service needs the chat model
config (`CHAT_*`) and optional booru credentials. **1Password** is supported (keep
`op://` references in `.env`, launch with `op run --env-file=.env -- …`); a
plaintext `.env` is the fallback and is gitignored. Logging is configured once at
each entrypoint; the level comes from `LOG_LEVEL`.

The **Message Content** privileged intent is required for the frontend (the
conversational entrypoint reads message text).

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
