"""The booru skill package: the ``derpi``, ``furbooru``, and ``e621`` search skills.

The entry-point factories (:func:`build_derpi`, :func:`build_furbooru`,
:func:`build_e621`) read the worker's
:class:`~petbot.skills.booru.settings.BooruSettings` and inject a shared
``httpx.AsyncClient`` — the per-skill ``build(settings)`` wiring the worker uses
in place of zero-arg construction.
"""

from __future__ import annotations

import httpx

from petbot.skills.booru.settings import BooruSettings
from petbot.skills.booru.skill import DerpiSkill, E621Skill, FurbooruSkill

__all__ = [
    "DerpiSkill",
    "E621Skill",
    "FurbooruSkill",
    "build_derpi",
    "build_e621",
    "build_furbooru",
]

#: One client shared by the worker's booru skills (connection reuse).
_client: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=20.0)
    return _client


def build_derpi() -> DerpiSkill:
    """Build the Derpibooru skill from the environment."""
    settings = BooruSettings()
    return DerpiSkill(client=_shared_client(), api_key=settings.derpibooru_api_key)


def build_furbooru() -> FurbooruSkill:
    """Build the Furbooru skill from the environment."""
    settings = BooruSettings()
    return FurbooruSkill(client=_shared_client(), api_key=settings.furbooru_api_key)


def build_e621() -> E621Skill:
    """Build the e621 skill from the environment."""
    settings = BooruSettings()
    return E621Skill(
        client=_shared_client(),
        user_agent=settings.user_agent,
        username=settings.e621_username,
        api_key=settings.e621_api_key,
    )
