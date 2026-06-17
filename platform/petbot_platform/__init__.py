"""PetBot runtime: the worker (run skills) and the edge's remote dispatch."""

from __future__ import annotations

from petbot_platform.dispatch import HttpDispatch
from petbot_platform.serve import serve
from petbot_platform.worker import SKILLS_GROUP, Worker

__all__ = ["SKILLS_GROUP", "HttpDispatch", "Worker", "serve"]
