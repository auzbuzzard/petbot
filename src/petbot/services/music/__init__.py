"""The music service: a gateway + voice host behind a dispatch endpoint."""

from __future__ import annotations

from petbot.services.music.bot import MusicService, run

__all__ = ["MusicService", "run"]
