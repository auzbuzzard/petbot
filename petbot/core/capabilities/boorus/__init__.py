"""Booru (imageboard) search providers, modernized and platform-neutral.

Each provider module (:mod:`derpibooru`, :mod:`e621`) exposes the same shape:
argument parsing, an async :class:`SearchQuery`, response parsing, and a builder
that returns a neutral :class:`~petbot.core.skills.context.SkillResult`. HTTP is
performed through an injected :class:`aiohttp.ClientSession` (no module-global
connection pool).
"""

from __future__ import annotations
