import asyncio
import contextlib
import fcntl
import hashlib
import os
import re
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import IO, Any
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

#: Redis 논리 DB는 0~15, 16개뿐이다. 이보다 많은 워커가 뜨면 `% 16`으로
#: 조용히 겹치게 두지 않고 아래 `initialize`에서 바로 실패시킨다.
REDIS_LOGICAL_DB_COUNT = 16

#: 실행끼리 자리를 나누고 싶을 때 준다 — `TEST_SLOT=1 uv run pytest`.
TEST_SLOT_ENV = "TEST_SLOT"

#: MySQL 「Access denied for user ... to database ...」 — 자리별 DB 를 만들 권한이 없을 때.
_ACCESS_DENIED_DB = 1044

#: 보유자 PID 를 다시 읽어 보는 횟수와 간격 — 빈 창은 마이크로초 단위다.
_HOLDER_READ_TRIES = 5
_HOLDER_READ_WAIT = 0.02


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


def run_slot() -> int:
    """이 실행이 쓸 자리 — **DB 이름과 Redis 논리 DB를 함께** 정한다.

    위 독스트링이 적은 사고는 워커끼리만 막혀 있었다. `PYTEST_XDIST_WORKER` 는
    **한** `pytest` 프로세스 안의 워커에만 붙으므로, 따로 띄운 두 실행은 둘 다
    `worker_index is None` 이라 **둘 다** `test` 를 쓴다. 그래서 늦게 시작한 쪽이
    먼저 돌던 쪽의 스키마를 통째로 지운다 (KEY-282 — 실제로 겪었다. 멀쩡한 검사가
    빨갛게 나왔고, 두 실행이 22분을 서로 막았다).

    자리를 **하나의 번호**로 모은다. 둘을 따로 정하면 「이름은 갈렸는데 Redis 는
    겹친」 조합이 생기고, 그것은 세션·로그인시도 카운터에서만 드러나 찾기 어렵다.

        TEST_SLOT 없음 · xdist 없음   →  0
        TEST_SLOT 없음 · gw3          →  3        (예전과 같다)
        TEST_SLOT=4    · xdist 없음   →  4
        TEST_SLOT=4    · gw3          →  7        (겹치지 않게 더한다)
    """
    raw = os.environ.get(TEST_SLOT_ENV, "0").strip() or "0"
    if not raw.isdigit():
        raise RuntimeError(f"{TEST_SLOT_ENV} 는 0 이상의 정수여야 한다 — 받은 값 {raw!r}")
    return int(raw) + (_xdist_worker_index() or 0)


def test_db_name(slot: int | None = None) -> str:
    """자리 0 은 예전 그대로 `test` — 아무것도 안 주고 돌리던 사람에게 영향이 없다."""
    slot = run_slot() if slot is None else slot
    return "test" if slot == 0 else f"test_{slot}"


def _slot_lock_path(db_name: str) -> Path:
    """**서버까지 포함해 잠근다** — 다른 MySQL 을 보는 실행끼리는 안 막아야 한다."""
    key = f"{config.DB_HOST}:{config.DB_PORT}/{db_name}"
    return Path(tempfile.gettempdir()) / f"ah05-test-db-{hashlib.sha256(key.encode()).hexdigest()[:16]}.lock"


#: 잡은 잠금을 세션 끝까지 들고 있는다. 프로세스가 죽으면 OS 가 알아서 푼다 —
#: 그래서 `kill -9` 로 끊긴 실행이 남긴 잠금을 사람이 치울 일이 없다.
_slot_lock: IO[str] | None = None


def _holder_pid(handle: IO[str]) -> str:
    """잠금을 쥔 쪽의 PID — **잠깐 기다렸다 다시 읽는다.**

    `O_CREAT` 로 파일이 **생긴 순간**과 이긴 쪽이 PID 를 **쓰는 순간** 사이에
    빈 창이 있다. 지는 쪽이 하필 그때 읽으면 보유자가 빈다 — 여섯이 동시에
    달려들면 실제로 난다(고치기 전 60판에 102회, 쓰기 순서를 바로잡은 뒤에도 60회).
    쓰는 쪽이 잠금을 이미 쥐고 있으므로 **반드시 곧 쓴다.** 그래서 짧게 몇 번만
    다시 본다. 못 읽어도 그냥 없이 간다 — 진단용이지 잠금의 정확성이 아니다.
    """
    for _ in range(_HOLDER_READ_TRIES):
        handle.seek(0)
        found = handle.read().strip()
        if found:
            return found
        time.sleep(_HOLDER_READ_WAIT)
    return ""


def _hold_slot(db_name: str) -> None:
    """이 자리를 이미 누가 쓰고 있으면 **그 자리에서 멈춘다.**

    조용히 진행하면 남의 스키마를 지운다. 같은 파일 아래쪽에서 워커가 16을 넘을 때
    `% 16` 으로 감싸지 않고 죽이는 것과 같은 태도다 — 겹치는 것보다 우는 편이 낫다.
    """
    global _slot_lock
    #: **`"w"` 도 `"a+"` 도 안 된다** — 이희진 님 `#240` ⑤.
    #:
    #: `"w"` 는 `flock` 을 걸기 **전에** 파일을 비워서, 지는 쪽이 여는 것만으로
    #: 보유자가 적어 둔 PID 를 지운다. 그래서 `"a+"` 로 바꿨는데 그것도 틀렸다 —
    #: 덧붙이기 모드는 `seek(0)` 을 무시하고 **끝에** 쓰므로, 이긴 쪽이 먼저
    #: `truncate()` 를 해야 했고 그 사이 **0바이트 창**이 생겼다. 진 쪽이 하필
    #: 그때 읽으면 보유자가 빈다(이희진 님이 26회에 1회로 재현하셨다).
    #:
    #: `O_RDWR | O_CREAT` 는 비우지도, 끝으로 밀지도 않는다. 그래서 **쓰고 나서
    #: 자르면** 창이 아예 없다.
    fd = os.open(_slot_lock_path(db_name), os.O_RDWR | os.O_CREAT, 0o600)
    handle = os.fdopen(fd, "r+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        holder = _holder_pid(handle)
        handle.close()
        raise RuntimeError(
            f"검사 DB `{db_name}` 을 이미 다른 pytest 실행이 쓰고 있다 "
            f"({config.DB_HOST}:{config.DB_PORT}" + (f", pid {holder}" if holder else "") + ").\n"
            f"  그대로 두면 늦게 시작한 쪽이 먼저 돌던 쪽의 스키마를 지워, "
            f"둘 다 틀린 결과를 낸다 (KEY-282).\n"
            f"  나란히 돌리려면 자리를 달리 준다 — `{TEST_SLOT_ENV}=1 uv run pytest ...`"
        ) from None
    #: **쓰고 나서 자른다** — 그 반대로 하면 0바이트 창이 생긴다.
    handle.seek(0)
    handle.write(str(os.getpid()))
    handle.truncate()
    handle.flush()
    _slot_lock = handle


def _release_slot() -> None:
    global _slot_lock
    if _slot_lock is not None:
        #: **비우고 놓는다.** 안 그러면 다음에 지는 쪽이 **이미 죽은 실행의 PID** 를
        #: 보유자로 읽는다 (이희진 님 `#240` ⑤). 아직 잠금을 쥔 채라 안전하다.
        with contextlib.suppress(OSError, ValueError):
            _slot_lock.seek(0)
            _slot_lock.truncate()
        _slot_lock.close()  # 닫으면 flock 도 풀린다
        _slot_lock = None


def _is_access_denied(error: BaseException, db_name: str) -> bool:
    """이 예외가 「그 DB 에 접근 거부(1044)」인가 — **감싸여 있어도 알아본다.**

    처음에는 `isinstance(error, asyncmy.errors.OperationalError)` 로 갈랐는데
    (이희진 님 `#240` ④) **실제 경로에서 한 번도 안 걸렸다.** 검사 DB 는
    `db_create()` → `execute_script()` 로 만들어지고 그 메서드에는 tortoise 의
    `@translate_exceptions` 가 붙어 있어, asyncmy 예외를
    `tortoise.exceptions.OperationalError(exc)` 로 **다시 던진다.** 그러면
    타입도 다르고 `args[0]` 도 코드가 아니라 감싼 예외 객체다.

    그래서 **껍질을 벗겨 가며** 코드를 찾는다. 그러고도 못 찾으면 서버 메시지를
    본다 — 드라이버가 또 바뀌어도 `str()` 은 래핑을 통과한다. 고치기 전의 문자열
    매칭이 이 점에서는 오히려 견고했다.
    """
    node: BaseException | None = error
    for _ in range(5):  # 껍질이 무한히 깊을 리는 없다
        if node is None:
            break
        if node.args and node.args[0] == _ACCESS_DENIED_DB:
            return True
        inner = node.args[0] if node.args and isinstance(node.args[0], BaseException) else None
        node = inner or node.__cause__
    return f"to database '{db_name}'" in str(error)


def _explained(error: BaseException, db_name: str) -> BaseException:
    """권한이 없어 죽은 것이면 **무엇을 하면 되는지**까지 얹어 준다.

    앱 유저는 `CREATE DATABASE` 를 못 하고 권한은 이름마다 따로 있어야 한다
    (`infra/docker/initdb.d/01-test-db.sql`). 그런데 그 파일은 **볼륨이 빌 때
    한 번만** 돌아서, 이미 MySQL 을 띄워 둔 사람에게는 안 적용된다. 그대로 두면
    `(1044, "Access denied ...")` 한 줄과 setup 오류 수십 개만 보인다.
    """
    if not _is_access_denied(error, db_name):
        return error
    return RuntimeError(
        f"검사 DB `{db_name}` 을 만들 권한이 없다.\n"
        f"  `initdb.d` 는 MySQL 볼륨이 빌 때 한 번만 도는데, 이미 띄워 둔 판에는 안 적용된다.\n"
        f"  한 번만 넣어 주면 된다 —\n"
        f'    docker exec mysql mysql -u root -p"$DB_ROOT_PASSWORD" \\\n'
        f"      -e \"GRANT ALL ON \\`test\\\\_%\\`.* TO '{config.DB_USER}'@'%'; FLUSH PRIVILEGES;\"\n"
        f"  ({TEST_SLOT_ENV} 없이 그냥 돌리면 `test` 를 쓰므로 이 권한이 필요 없다.)"
    )


def get_test_db_config() -> dict[str, Any]:
    db_name = test_db_name()
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
    slot = run_slot()
    if slot >= REDIS_LOGICAL_DB_COUNT:
        # `% 16`으로 감싸면 17번째 자리부터 남의 세션·로그인시도 카운터를
        # 조용히 밟는다 — 시간이 지나 CI 러너 코어가 늘면 재발할 수 있는
        # 자리라, 겹치게 두지 않고 여기서 바로 죽인다(한금준 님 리뷰).
        raise RuntimeError(
            f"검사 자리가 {REDIS_LOGICAL_DB_COUNT}개를 넘었다(자리 {slot}) — "
            f"Redis 논리 DB는 0~{REDIS_LOGICAL_DB_COUNT - 1}뿐이라 그 이상은 서로 겹친다. "
            f"워커 수를 줄이거나 `{TEST_SLOT_ENV}` 를 낮춰라."
        )
    #: **설정한 값을 밑자리로 삼는다** — 이희진 님 `#240` ⑥.
    #:
    #: 예전에는 xdist 안에서만 넣어서 따로 띄운 두 실행이 둘 다 0번을 밟았다.
    #: 그렇다고 무조건 `= slot` 으로 덮으면, `REDIS_DB` 를 손수 정해 두고 그냥
    #: `pytest` 를 돌리는 사람의 값이 조용히 0이 된다. 더해서 둘 다 산다.
    base_redis = config.REDIS_DB or 0
    if base_redis + slot >= REDIS_LOGICAL_DB_COUNT:
        raise RuntimeError(
            f"Redis 논리 DB 가 모자란다 — 밑자리 {base_redis} + 자리 {slot} 이 "
            f"{REDIS_LOGICAL_DB_COUNT} 를 넘는다. `REDIS_DB` 를 낮추거나 워커를 줄여라."
        )
    config.REDIS_DB = base_redis + slot

    db_name = test_db_name(slot)
    _hold_slot(db_name)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with patch("tortoise.contrib.test.getDBConfig", Mock(return_value=get_test_db_config())):
            initializer(modules=TORTOISE_APP_MODELS)
    except BaseException as error:
        _release_slot()  # 초기화가 죽어도 자리를 붙들고 있지 않는다
        raise _explained(error, db_name) from error
    yield

    #: **자리를 놓는 일은 반드시 한다** — 이희진 님 `#240` ①.
    #:
    #: `finalizer()` 나 `loop.close()` 가 예외를 던지면 `_release_slot()` 이 안
    #: 돌았다. pytest 는 teardown 예외에도 곧장 안 죽고 다른 finalizer·커버리지
    #: 리포트·요약까지 마치므로, 그 사이 같은 자리를 쓰는 두 번째 실행이 「이미
    #: 다른 pytest 실행이 쓰고 있다」를 맞는다 — 이 파일이 막으려던 그 상황이다.
    try:
        finalizer()
        loop.close()
    finally:
        _release_slot()


@pytest_asyncio.fixture(autouse=True, scope="session")  # type: ignore[type-var]
def event_loop() -> None:
    pass
