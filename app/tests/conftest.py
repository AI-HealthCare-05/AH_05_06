import asyncio
import os
import re
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


def _xdist_worker_index() -> int | None:
    """pytest-xdist 워커 번호. xdist 없이 돌면 `None`(기존 동작 그대로).

    `tortoise.contrib.test.initializer()/finalizer()`는 세션마다 고정된 DB
    이름을 통째로 drop→재생성한다 — 워커마다 그대로 두면 서로 남의 스키마를
    지운다. 실 Redis 를 쓰는 세션/로그인시도 검사들도 `staff_id`·`login_id`
    같은 워커 무관 키를 쓰므로, DB 이름과 Redis 논리 DB를 같은 번호로 나눈다.
    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker_id:
        return None
    match = re.search(r"\d+", worker_id)
    return int(match.group()) if match else 0


def get_test_db_config() -> dict[str, Any]:
    worker_index = _xdist_worker_index()
    db_name = "test" if worker_index is None else f"test_gw{worker_index}"
    tortoise_config = generate_config(
        db_url=f"mysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{db_name}",
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
    worker_index = _xdist_worker_index()
    if worker_index is not None:
        # Redis 는 논리 DB가 16개(0~15)뿐이라 워커 수가 그보다 많아지면 겹친다 —
        # `-n auto` 는 러너 코어 수만큼만 띄우므로 지금 CI 규모에서는 안전하다.
        config.REDIS_DB = worker_index % 16

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
