from __future__ import annotations

from datetime import datetime, timezone

from lifeguard.backend_models import BuildDoc, ItemRef
from lifeguard.config import load_config
from lifeguard.firestore_client import init_firestore
from lifeguard.firestore_repo import (
    upsert_guild,
    upsert_player,
    upsert_zone,
    write_build,
)


def main() -> int:
    config = load_config()
    client = init_firestore(config)

    if client is None:
        raise SystemExit(
            "Firebase is disabled. Set FIREBASE_ENABLED=true (and credentials) in .env."
        )

    try:
        upsert_guild(client, name="SmokeTest Guild")
        upsert_zone(client, name="SmokeTest Zone")
        upsert_player(client, name="SmokeTest Player", guild_name="SmokeTest Guild")

        build_id = write_build(
            client,
            build=BuildDoc(
                player_name="SmokeTest Player",
                guild_name="SmokeTest Guild",
                zone_name="SmokeTest Zone",
                created_at=datetime.now(timezone.utc),
                source="smoke-test",
                main_hand=ItemRef(item_id="T4_MAIN_SWORD"),
            ),
        )
    except Exception as exc:
        # Avoid a giant stacktrace for common setup problems.
        try:
            from google.api_core import exceptions as gexc

            if isinstance(exc, gexc.NotFound):
                raise SystemExit(
                    "Firestore database not found for this project.\n"
                    "Enable Firestore in Firebase Console (Build -> Firestore Database -> Create database),\n"
                    "then re-run this smoke test.\n"
                    "If you enabled it already, double-check FIREBASE_PROJECT_ID points at the right project."
                )
            if isinstance(exc, gexc.PermissionDenied):
                raise SystemExit(
                    "Permission denied talking to Firestore.\n"
                    "Check that your service account JSON is for the same project and has Firestore access."
                )
        except Exception:
            # If google.api_core isn't available for some reason, fall through.
            pass
        raise

    print(f"Firestore smoke test OK. Wrote builds/{build_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
