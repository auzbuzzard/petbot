"""Run the edge: ``python -m petbot.discord`` (or via the ``petbot-edge`` script)."""

from __future__ import annotations

from petbot.discord.bot import run
from petbot.discord.settings import EdgeSettings


def main() -> None:
    run(EdgeSettings())  # fields are read from the environment


if __name__ == "__main__":
    main()
