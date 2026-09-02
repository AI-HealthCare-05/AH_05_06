import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from _pytest.fixtures import FixtureRequest
from tortoise import generate_config
from tortoise.contrib.test import finalizer, initializer

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS, TORTOISE_ORM

TEST_BASE_URL = "http://test"
TEST_DB_LABEL = "models"
TEST_DB_TZ = "Asia/Seoul"


def get_test_db_config() -> dict[str, Any]:
    tortoise_config = generate_config(
        db_url=f"mysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/test",
        app_modules={TEST_DB_LABEL: TORTOISE_APP_MODELS},
        connection_label=TEST_DB_LABEL,
        testing=True,
    )
    #: **검사 판의 시계를 앱과 같게 맞춘다.**
    #:
    #: `generate_config` 는 `use_tz` 를 안 정하고 기본값(False)으로 둔다.
    #: 앱은 `True` 였다 — 그래서 **검사와 서버가 다른 시계로 돌았고**,
    #: `auto_now_add` 가 아홉 시간 어긋나는 것을 검사가 통째로 못 봤다
    #: (링크 만료와 인증번호 잠금이 즉시 풀리던 것도 같은 뿌리다).
    #:
    #: 값을 여기 적지 않고 `TORTOISE_ORM` 에서 읽어 온다 — 적어 두면 한쪽만
    #: 바뀌는 날 같은 일이 되풀이된다.
    tortoise_config["timezone"] = TORTOISE_ORM.get("timezone", TEST_DB_TZ)
    tortoise_config["use_tz"] = TORTOISE_ORM["use_tz"]

    return tortoise_config


@pytest.fixture(scope="session", autouse=True)
def initialize(request: FixtureRequest) -> Generator[None, None]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with patch("tortoise.contrib.test.getDBConfig", Mock(return_value=get_test_db_config())):
        initializer(modules=TORTOISE_APP_MODELS)
    yield
    finalizer()
    loop.close()


@pytest_asyncio.fixture(autouse=True, scope="session")  # type: ignore[type-var]
def event_loop() -> None:
    pass
