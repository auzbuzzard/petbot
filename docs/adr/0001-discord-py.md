# ADR 0001: Build on discord.py

- Status: Accepted
- Date: 2026-05-30

## Context

PetBot must run on Discord. Discord has **no first-party bot SDK** — the official
surface is the raw REST + Gateway API and an OpenAPI spec; every library
(`discord.py`, `discord.js`, …) is community-maintained. We also want to reuse
the existing Python booru/`numexpr` logic and keep the door open for a future
Python-based LLM tooling layer.

The main risk with `discord.py` is bus factor: it is effectively single-maintainer
and was briefly discontinued in 2021 before being revived in 2022.

## Decision

Use **`discord.py` 2.x** (Python 3.11+).

We hedge the bus-factor risk architecturally: skill logic carries **no `discord`
import** (see ADR 0003), so a swap to a near-drop-in fork (Pycord, nextcord)
would touch only the Discord adapter, not the core.

## Consequences

- Stay in Python end-to-end; reuse booru logic; small, auditable dependency tree.
- Slash-command first via `app_commands`/`CommandTree`; the privileged Message
  Content intent is avoided until a chat/LLM layer needs it.
- If `discord.py` stalls again, the migration is confined to `frontends/discord/`.
