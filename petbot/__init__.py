"""PetBot: a modern, slash-command-first Discord bot with a platform-neutral core.

The package is split into two halves with a strict, one-way dependency rule:

* ``petbot.core`` — platform-neutral logic (skills, the skill registry, ports,
  booru capabilities). It never imports ``discord`` or ``petbot.frontends``.
* ``petbot.frontends`` — adapters that translate a platform's events into core
  calls and render :class:`~petbot.core.skills.context.SkillResult` back. Only
  the Discord adapter is built today.

See ``docs/architecture.md`` for the rationale and the request flow.
"""

from __future__ import annotations

__version__ = "2.0.0"
