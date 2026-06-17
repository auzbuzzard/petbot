"""Run the music worker: ``python -m petbot.workers.music``."""

from __future__ import annotations

from petbot.workers.music.bot import run
from petbot.workers.music.settings import MusicSettings


def main() -> None:
    run(MusicSettings())  # fields are read from the environment


if __name__ == "__main__":
    main()
