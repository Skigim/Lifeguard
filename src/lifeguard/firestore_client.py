from __future__ import annotations

from pathlib import Path
from typing import Any

from lifeguard.config import Config


def init_firestore(config: Config):
    """Initialize Firebase Admin SDK and return a Firestore client.

    Returns None when Firebase is disabled.

    Notes:
    - Uses a service-account JSON when FIREBASE_CREDENTIALS_PATH is provided.
    - Otherwise relies on Application Default Credentials (ADC).
    """

    if not config.firebase_enabled:
        return None

    import firebase_admin
    from firebase_admin import credentials, firestore

    options: dict[str, Any] = {}
    if config.firebase_project_id:
        options["projectId"] = config.firebase_project_id

    try:
        app = firebase_admin.get_app()
    except ValueError:
        cred = None
        if config.firebase_credentials_path:
            cred_path = Path(config.firebase_credentials_path)
            if not cred_path.exists():
                raise ValueError(
                    f"FIREBASE_CREDENTIALS_PATH does not exist: {cred_path}"
                )
            cred = credentials.Certificate(str(cred_path))

        app = firebase_admin.initialize_app(cred, options or None)

    return firestore.client(app=app)
