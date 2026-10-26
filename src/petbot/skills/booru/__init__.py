from __future__ import annotations

import httpx

from petbot.skills.booru.settings import BooruSettings
from petbot.skills.booru.skill import DerpiSkill, E621Skill

__all__ = ["DerpiSkill", "E621Skill", "build_derpi", "build_e621"]

#: One client shared by the service's booru skills (connection reuse).
_client: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=20.0)
    return _client


def build_derpi() -> DerpiSkill:
    settings = BooruSettings()
    return DerpiSkill(client=_shared_client(), api_key=settings.derpibooru_api_key)


def build_e621() -> E621Skill:
    settings = BooruSettings()
    return E621Skill(
        client=_shared_client(),
        user_agent=settings.user_agent,
        username=settings.e621_username,
        api_key=settings.e621_api_key,
    )
