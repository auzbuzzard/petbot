"""Run the Discord frontend: ``python -m petbot.frontends.discord``."""

from __future__ import annotations

from petbot.frontends.discord.bot import run
from petbot.frontends.discord.settings import DiscordSettings


def main() -> None:
    run(DiscordSettings())  # fields are read from the environment


if __name__ == "__main__":
    main()
