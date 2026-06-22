"""PetBot Discord frontend: the always-on gateway that dispatches to a compute service."""

from __future__ import annotations

from petbot.frontends.discord.bot import PetBot, run
from petbot.frontends.discord.settings import EdgeSettings

__all__ = ["EdgeSettings", "PetBot", "run"]
