from __future__ import annotations

from petbot.frontends.discord.bot import run
from petbot.frontends.discord.settings import DiscordSettings
from petbot.platform.secrets import load_ssm_secrets


def main() -> None:
    load_ssm_secrets()  # the deployed edge's token comes from SSM (see SSM_SECRETS)
    run(DiscordSettings())


if __name__ == "__main__":
    main()
