"""Booru (imageboard) search providers, platform-neutral.

Layout:

- :mod:`tags` — the abstract search vocabulary (``SystemTag`` → ``Sort``/
  ``Rating``/``FileType``) and the ``Range`` numeric concept, shared by all sites.
- :mod:`types` — neutral ``SearchRequest`` in, ``Post`` out (frozen dataclasses).
- :mod:`base` — the ``BooruProvider`` protocol the engine talks to.
- :mod:`engine` — the shared ``run_search`` every provider flows through (httpx).
- :mod:`render` — ``Post`` → neutral ``SkillResult`` (plus the greeter).
- :mod:`derpibooru`, :mod:`e621` — each owns its full native ``Sort``/``Rating``/
  ``FileType`` vocabulary, pydantic response models, and request serialization.
"""

from __future__ import annotations
