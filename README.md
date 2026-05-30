# PetBot

A modern, slash-command-first Discord bot. PetBot searches imageboards
(Derpibooru, e621/e926), evaluates math expressions, and plays audio in voice
channels — all behind a **platform-neutral core** so the same skills can power
other frontends (Telegram, web, an LLM chat layer) later.

This is the 2.0 revival of a 2018 bot. The original (built on the long-removed
`discord.py` 0.16 "async" branch) is preserved at the git tag
**`v0.1-legacy-2018`**.

## Features

| Command | What it does |
| --- | --- |
| `/ping` | Liveness check. |
| `/math expression:<expr>` | Evaluate an arithmetic expression (`numexpr`). |
| `/derpi tags:<tags>` | Search Derpibooru. |
| `/e621 tags:<tags>` | Search e621/e926. |
| `/music play\|skip\|stop\|queue\|volume` | Voice playback with a queue and skip-votes. |
| `/purge count:<n>` | Bulk-delete messages (requires Manage Messages). |

Explicit booru results are only returned in age-restricted (NSFW) channels.

## Quickstart

Requirements: **Python 3.11+** and, for voice, the **FFmpeg** system binary.

```bash
pip install -e ".[dev]"      # install PetBot + dev tooling
cp .env.example .env         # then fill in your secrets/references
```

### Configuration

All configuration is read from the environment (see `.env.example` for the full
list). The required variable is `DISCORD_TOKEN`; `DEV_GUILD_ID` enables instant
slash-command sync while developing.

**Recommended — 1Password (no plaintext secrets on disk):** keep the `op://`
references in `.env` and launch with:

```bash
op run --env-file=.env -- python -m petbot
```

`op run` resolves the references into the process environment at start-up.

**Fallback — plaintext `.env`:** replace the `op://...` values with real secrets
and run:

```bash
python -m petbot
```

`.env` is gitignored; never commit it with real secrets.

### Discord Developer Portal setup

- Enable the **Server Members**/**Voice** intents as needed. PetBot uses the
  default intents plus **Voice States** for music.
- The **Message Content** privileged intent is **not** required — slash commands
  don't need it. It only becomes necessary if/when the Phase B chat/LLM layer
  lands.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — how the neutral core and the
  Discord adapter fit together (the *why*).
- [`docs/contributing.md`](docs/contributing.md) — adding a skill or a frontend;
  running lint/type/test.
- [`docs/adr/`](docs/adr/) — the load-bearing architectural decisions.
- [`AGENTS.md`](AGENTS.md) — high-signal guide for AI agents working in this repo.

## Development

```bash
ruff check . && ruff format --check .   # lint + format
mypy                                    # strict type-check
lint-imports                            # enforce core/adapter boundary
pytest                                  # tests (fully offline)
pre-commit install                      # run the gates on every commit
```

CI runs all of the above on every push and pull request. It needs **no
secrets** — every test is offline (mocked APIs, no Discord login).
