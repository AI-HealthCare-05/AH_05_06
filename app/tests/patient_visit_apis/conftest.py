import os
from collections.abc import Generator

import pytest
from tortoise.contrib.test import finalizer, initializer

from app.core.db.databases import TORTOISE_APP_MODELS


@pytest.fixture(scope="session", autouse=True)
def optional_sqlite_database() -> Generator[None, None]:
    """Offer an explicit local fallback; CI keeps using the repository MySQL fixture."""
    if os.getenv("KEY34_SQLITE_TEST") != "1":
        yield
        return

    initializer(modules=TORTOISE_APP_MODELS, db_url="sqlite://:memory:")
    yield
    finalizer()
