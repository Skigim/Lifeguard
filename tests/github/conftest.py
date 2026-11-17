import json
from pathlib import Path

import pytest

from lifeguard.features.github.store import Store


@pytest.fixture
async def store():
    db = await Store.open(":memory:")
    yield db
    await db.close()


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures" / "issue.json").read_text())
