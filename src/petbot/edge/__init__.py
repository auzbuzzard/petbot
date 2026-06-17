"""PetBot Discord edge: the always-on gateway that dispatches to skill workers."""

from __future__ import annotations

from petbot.edge.bot import PetBot, run
from petbot.edge.settings import EdgeSettings

__all__ = ["EdgeSettings", "PetBot", "run"]
