"""Run the edge: ``python -m petbot.edge`` (or via the ``petbot-edge`` script)."""

from __future__ import annotations

from petbot.edge.bot import run
from petbot.edge.settings import EdgeSettings


def main() -> None:
    run(EdgeSettings())  # fields are read from the environment


if __name__ == "__main__":
    main()
