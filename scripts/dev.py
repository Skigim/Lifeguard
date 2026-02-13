"""Hot-reload dev runner for the test bot.

Usage:
    python scripts/dev.py

Watches ``src/`` for file changes and automatically restarts the bot
with ``BOT_ENV=test``.  The production bot (if running) is unaffected
because Python keeps code in memory — only the dev process restarts.

Requires: ``pip install watchfiles``
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Force test environment so the dev runner never touches production
    os.environ["BOT_ENV"] = "test"

    try:
        from watchfiles import run_process  # type: ignore[import-untyped]
    except ImportError:
        print(
            "watchfiles is not installed. Run:  pip install watchfiles",
            file=sys.stderr,
        )
        return 1

    print("🔄 Starting dev server (BOT_ENV=test) — watching src/ for changes…")
    print("   Press Ctrl+C to stop.\n")

    run_process(
        "src",
        target=_run_bot,
        callback=_on_reload,
        watch_filter=_py_filter,
    )
    return 0


def _run_bot() -> None:
    """Import and run the bot entry-point in a child process."""
    from lifeguard.__main__ import main as bot_main

    bot_main()


def _on_reload(changes: set) -> None:  # noqa: ANN001
    changed_files = ", ".join(
        str(c[1]).replace("\\", "/").split("src/")[-1] for c in changes
    )
    print(f"\n🔄 Change detected: {changed_files}  — restarting…\n")


def _py_filter(change: object, path: str) -> bool:
    """Only watch Python source files."""
    return path.endswith(".py")


if __name__ == "__main__":
    raise SystemExit(main())
