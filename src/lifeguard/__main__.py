from __future__ import annotations

import sys

from lifeguard.bot import create_bot
from lifeguard.config import load_config
from lifeguard.logging_config import configure_logging


def main() -> int:
    config = load_config()
    configure_logging(config.log_level)

    if not config.discord_token:
        print(
            "Missing DISCORD_TOKEN. Create a .env file (see .env.example) and set DISCORD_TOKEN.",
            file=sys.stderr,
        )
        return 2

    bot = create_bot(config)
    bot.run(config.discord_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
