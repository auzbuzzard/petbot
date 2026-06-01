"""Booru (imageboard) search providers, platform-neutral.

Layout:

- :mod:`types` — neutral ``SearchRequest`` in, ``Post`` out (frozen dataclasses).
- :mod:`http` — the injected ``aiohttp`` seam (structural protocols only).
- :mod:`base` — the per-site model contract (``BooruResponse`` / ``ErrorResponse``)
  and the ``BooruProvider`` protocol the engine talks to.
- :mod:`engine` — the shared ``run_search`` every provider flows through.
- :mod:`render` — ``Post`` → neutral ``SkillResult`` (plus the greeter).
- :mod:`derpibooru`, :mod:`e621` — each owns its ``Sort``/``Rating`` vocabulary,
  pydantic models, and a small provider that shapes the request.
"""

from __future__ import annotations
