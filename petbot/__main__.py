"""Entry point: ``python -m petbot``.

Loads a plaintext ``.env`` if present (the no-1Password fallback), builds
:class:`Settings` from the environment, and starts the Discord frontend. With
1Password, run ``op run --env-file=.env -- python -m petbot`` instead — the env
is already populated and the ``.env`` load below is a harmless no-op.
"""

from __future__ import annotations

from dotenv import load_dotenv

from petbot.config import Settings
from petbot.frontends.discord import bootstrap


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    bootstrap.run(settings)


if __name__ == "__main__":
    main()
