"""The core worker hosts math + booru + chat, with chat wired to its siblings."""

from __future__ import annotations

from petbot.workers.core import build_worker


def test_build_worker_hosts_all_core_skills() -> None:
    names = build_worker().skill_names
    assert {"math", "derpi", "e621", "chat"} <= names
    assert "music" not in names  # music is its own worker
