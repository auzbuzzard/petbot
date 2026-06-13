"""Entry point: ``python -m petbot`` — starts the Discord **gateway** frontend.

The gateway is PetBot's parked ``/music`` worker; the blessed deploy path is the
serverless HTTP-Interactions Lambda (see ADR 0005). Configuration is read from
the process environment and a local ``.env`` if present (pydantic-settings loads
it), so ``op run --env-file=.env -- python -m petbot`` and a plaintext ``.env``
both work — and ``op run`` simply pre-populates the environment.
"""

from __future__ import annotations

from pydantic import ValidationError

from petbot.config import ConfigError, GatewaySettings
from petbot.frontends.discord import bootstrap


def main() -> None:
    try:
        settings = GatewaySettings()
    except ValidationError as exc:
        raise ConfigError(
            "Configuration is incomplete — the gateway needs DISCORD_TOKEN. Copy "
            ".env.example to .env and fill it in, then launch with "
            "`op run --env-file=.env -- python -m petbot` (or export the variables "
            f"yourself).\n\n{exc}"
        ) from exc
    bootstrap.run(settings)


if __name__ == "__main__":
    main()
