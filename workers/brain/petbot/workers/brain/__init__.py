"""The brain worker bundle: math + booru + chat, behind one dispatch endpoint."""

from __future__ import annotations

from petbot.workers.brain.worker import build_worker

__all__ = ["build_worker"]
