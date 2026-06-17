"""PetBot Discord edge: the always-on gateway that dispatches to skill workers."""

from __future__ import annotations

from petbot.discord.bot import PetBot, run
from petbot.discord.settings import EdgeSettings

__all__ = ["EdgeSettings", "PetBot", "run"]
