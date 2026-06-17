"""The music worker bundle: a gateway + voice host behind a dispatch endpoint."""

from __future__ import annotations

from petbot.workers.music.bot import MusicWorker, run

__all__ = ["MusicWorker", "run"]
