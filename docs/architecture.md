# Architecture

PetBot is built as **ports & adapters** around a platform-neutral core. The goal:
the genuinely reusable logic (skills, booru search, the future LLM layer) never
knows it's talking to Discord, so adding Telegram, a web frontend, or swapping
`discord.py` for a fork is purely additive work at the edge.

## The dependency rule

```
petbot.frontends.discord  ──▶  petbot.core        (allowed)
petbot.core               ──X  petbot.frontends   (forbidden)
petbot.core               ──X  discord            (forbidden)
```

The core depends on nothing platform-specific. This is enforced two ways:

- **`import-linter`** (`lint-imports`) via the contracts in `pyproject.toml`.
- **`tests/test_core_isolation.py`**, which fails if any `petbot.core` module
  imports `discord` or `petbot.frontends`.

A change that violates the rule fails CI.

## Request flow

```
Discord event (slash command)
  └─ cog  (petbot/frontends/discord/cogs/*)
       ├─ build_context(interaction)          → SkillContext   (neutral in)
       ├─ skill.run(args, ctx)                 → SkillResult    (neutral out)
       └─ render.respond(interaction, result)  → discord.Embed + chunked text
```

The cog is the only thing that touches `discord`. It maps the interaction onto a
neutral [`SkillContext`](../petbot/core/skills/context.py), calls the skill, and
renders the [`SkillResult`](../petbot/core/skills/context.py) back. The skill
itself is pure with respect to the platform.

## Capability flags, not platform checks

A skill must never ask "am I on Discord?". It asks "can this conversation do X?"
via [`Capabilities`](../petbot/core/skills/context.py):

| Flag | Set by the Discord adapter from… |
| --- | --- |
| `allows_explicit` | `channel.is_nsfw()` |
| `supports_voice` | whether a `VoicePort` was injected |
| `supports_rich_embeds` | always true on Discord |
| `max_text_length` | Discord's 2000-char limit |

This keeps skills honest and portable: a future Telegram adapter sets the same
flags its own way, and the skills work unchanged.

## Ports

A **port** is an interface the core defines and an adapter implements, so neutral
logic can drive a platform capability without importing the platform. Today there
is one: [`VoicePort`](../petbot/core/skills/ports.py). The music skill owns the
queue and skip-vote logic; it plays audio through `ctx.voice`, which the Discord
adapter fills with [`DiscordVoicePort`](../petbot/frontends/discord/voice.py)
(yt-dlp extraction + `FFmpegPCMAudio`).

A skill declares `requires={"voice"}`; the
[`SkillRegistry`](../petbot/core/skills/registry.py) only offers it on frontends
whose `Capabilities` advertise that port. On a voice-less platform the skill is
simply never exposed.

`VoicePort.play` accepts an optional `on_finished` callback; the Discord adapter
invokes it (via the player's `after` hook, hopped back onto the event loop) when
a track ends on its own, so the music queue **auto-advances**. The skill guards
against stale callbacks with a per-conversation play token, so an explicit
`/music skip` or `/music stop` never double-advances.

## Rendering is per-platform

[`SkillResult`](../petbot/core/skills/context.py) carries an optional
`EmbedSpec` (a neutral description of a rich card) — never a `discord.Embed`.
Turning that into a `discord.Embed`, and splitting long text into ≤2000-char
messages, lives entirely in
[`render.py`](../petbot/frontends/discord/render.py). A Telegram adapter would
render the same `SkillResult` into its own 4096-char messages.

## Why this shape

See the ADRs in [`adr/`](adr/) for the load-bearing decisions: choosing
`discord.py`, deferring the LLM layer behind a provider-agnostic seam, and the
platform-neutral core. The short version: it keeps us in Python (reusing booru
logic and enabling future LLM tooling), hedges the single-maintainer risk of any
one Discord library, and makes new frontends additive rather than a rewrite.

## Where things live

```
petbot/
  config.py                     Settings (reads the environment only)
  core/                         PLATFORM-NEUTRAL — never imports discord
    skills/
      base.py                   the Skill ABC (name/description/input_schema/requires)
      context.py                SkillContext, SkillResult, Capabilities, EmbedSpec, …
      registry.py               name lookup + capability filtering
      ports.py                  VoicePort (and future ports)
      math_skill.py  booru_skill.py  music_skill.py
    capabilities/boorus/        modernized booru providers (async, neutral)
  frontends/
    discord/                    the only adapter built today
      bootstrap.py              intents, setup_hook, dependency wiring, tree sync
      context.py                interaction → SkillContext
      render.py                 SkillResult → discord.Embed + chunking
      voice.py                  VoicePort implementation
      cogs/                     slash-command wrappers
```
