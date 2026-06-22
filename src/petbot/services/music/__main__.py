"""Run the music service: ``python -m petbot.services.music``."""

from __future__ import annotations

from petbot.services.music.bot import run
from petbot.services.music.settings import MusicSettings


def main() -> None:
    run(MusicSettings())  # fields are read from the environment


if __name__ == "__main__":
    main()
