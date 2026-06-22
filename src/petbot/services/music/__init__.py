"""The music service: a gateway + voice host behind a dispatch endpoint."""

from __future__ import annotations

from petbot.services.music.bot import MusicWorker, run

__all__ = ["MusicWorker", "run"]
