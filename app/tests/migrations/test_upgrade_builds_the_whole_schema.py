"""빈 DB 에서 `aerich upgrade` 가 스키마를 통째로 세우는가 — KEY-206.

**이 검사가 없어서 Pilot 의 DB 가 코드보다 뒤처져 있었다.**

`deployment.sh` 에는 마이그레이션 단계가 없다. 이미지를 새로 올려도 DB 는
그대로 남는다. KEY-197 을 하다가 Pilot 에서 `guide_section.drug_caution_content_id`
가 통째로 없는 것을 발견했는데, 그건 사고가 아니라 **배포 경로가 원래 그렇게
생겨서** 나온 결과였다.

배포에 단계를 넣기 전에 그 명령이 정말 도는지부터 잰다. 여기서 재는 것은
문장이 아니라 **진짜 MySQL** 이다 — CI 가 `mysql:8.0` 을 띄운다.

두 가지를 본다.

1. 빈 DB 에 `upgrade` 를 걸면 **모델이 가진 표가 하나도 안 빠지고** 생긴다
2. 한 번 더 걸어도 **아무 일도 안 일어난다** — 배포는 매번 이걸 돈다.
   두 번째가 뭔가 한다면 그 배포는 굴릴 수 없다.
"""

import ast
import os
from pathlib import Path
from typing import Any

import pytest
from aerich import Command
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS, TORTOISE_ORM

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "app" / "core" / "db" / "migrations"

#: 이 검사만 쓰고 지우는 DB. 이름에 일감 번호를 박아 둔다 — 남의 DB 를 지우는
#: 사고가 나면 이름부터 눈에 띄어야 한다.
SCRATCH = "key206_upgrade_probe"


def _config_for(database: str) -> dict[str, Any]:
    """`TORTOISE_ORM` 을 그대로 두고 DB 이름만 바꾼 사본."""
    creds = dict(TORTOISE_ORM["connections"]["default"]["credentials"])  # type: ignore[index]
    creds["database"] = database
    return {
        **TORTOISE_ORM,
        "connections": {
            "default": {**TORTOISE_ORM["connections"]["default"], "credentials": creds}  # type: ignore[dict-item,index]
        },
    }


async def _sql(database: str | None, statement: str) -> list[Any]:
    """서버에 붙어 한 문장 돌린다. `database=None` 이면 DB 를 안 고르고 붙는다."""
    # `types-asyncmy` 는 안 넣는다 — 검사 하나 때문에 `uv.lock` 을 다시 풀어
    # 남의 설치를 흔들 자리가 아니다 (conftest 의 `yaml` 과 같은 판단).
    import asyncmy  # type: ignore[import-untyped]

    creds = TORTOISE_ORM["connections"]["default"]["credentials"]  # type: ignore[index]
    kwargs: dict[str, Any] = {
        "host": creds["host"],
        "port": creds["port"],
        "user": creds["user"],
        "password": creds["password"],
    }
    if database:
        kwargs["database"] = database
    conn = await asyncmy.connect(**kwargs)
    try:
        async with conn.cursor() as cur:
            await cur.execute(statement)
            return list(await cur.fetchall())
    finally:
        conn.close()


async def _make_scratch_database() -> None:
    """검사용 DB 를 만든다. 그 전에 **지워도 되는 이름인지부터** 확인한다.

    이 함수는 `DROP DATABASE` 로 시작한다. 그 이름이 설정된 DB 와 같아지는
    날이 오면 검사 한 번에 개발용 데이터가 사라진다. **실제로 한 번 사라뜨렸다** —
    이 검사를 만들면서 이름을 `ai_health` 로 바꿔 돌려 본 순간이었다.

    그때는 이름 확인이 **따로 있는 검사**였다. 그 검사는 빨갛게 울었지만
    아무것도 막지 못했다 — 우는 것과 막는 것은 다르다. 그래서 확인을
    지우는 자리 **안으로** 옮겼다.

    권한이 없을 때는 건너뛴다. 개발용 MySQL 계정에는 보통 `CREATE DATABASE`
    권한이 없고, 그 자리에서는 건너뛰는 게 맞다.

    **그런데 CI 에서 건너뛰면 이 검사는 있으나 마나다.** CI 는 일회용
    `mysql:8.0` 을 root 로 띄우므로 못 만들 이유가 없고, 못 만들었다면
    그건 건너뛸 일이 아니라 CI 가 망가진 것이다. 그래서 CI 에서는 운다.
    """
    from asyncmy.errors import OperationalError  # type: ignore[import-untyped]

    assert SCRATCH != config.DB_NAME, (
        f"검사용 DB 이름이 실제 DB 와 같다 ({SCRATCH}) — 이대로 지우면 개발 데이터가 날아간다"
    )

    try:
        await _sql(None, f"DROP DATABASE IF EXISTS {SCRATCH}")
        await _sql(None, f"CREATE DATABASE {SCRATCH} CHARACTER SET utf8mb4")
    except OperationalError as denied:
        if os.environ.get("GITHUB_ACTIONS"):
            raise AssertionError(
                f"CI 인데 검사용 DB 를 못 만들었다 — 빈 DB 마이그레이션 검사가 통째로 죽는다: {denied}"
            ) from denied
        pytest.skip(f"이 계정으로 `{SCRATCH}` 를 못 만든다 ({denied}). 빈 DB 마이그레이션 검사는 CI(root) 에서 돈다")


async def test_upgrade_builds_the_whole_schema_and_settles() -> None:
    """**빈 DB → 모든 표 → 두 번째는 무일.**

    둘을 한 검사에 담는다. 배포가 하는 일이 원래 하나이기 때문이다 — 「올리고
    또 올린다」. 나눠 놓으면 `Command` 가 잡고 있는 연결이 검사 사이에서 다른
    이벤트 루프에 걸려 검사 자체가 깨진다.
    """
    await _make_scratch_database()

    command = Command(tortoise_config=_config_for(SCRATCH), app="models", location=str(MIGRATIONS))
    try:
        await command.init()

        first = await command.upgrade(run_in_transaction=False)
        assert first, "빈 DB 인데 적용된 마이그레이션이 없다 — upgrade 가 아무것도 안 했다"

        # ① 모델이 아는 표가 하나도 안 빠졌는가.
        #    「개수가 맞다」로는 부족하다 — 개수는 맞고 이름이 다를 수 있다.
        Tortoise.init_models(TORTOISE_APP_MODELS, "models")
        wanted = {d["table"] for d in Tortoise.describe_models(serializable=True).values()}
        built = {row[0] for row in await _sql(SCRATCH, "SHOW TABLES")}
        missing = sorted(wanted - built)
        assert not missing, f"모델은 아는데 upgrade 가 안 만든 표 ({len(first)} 개 적용): {missing}"

        # ② 배포는 이걸 매번 돈다. 두 번째가 뭔가 한다면 굴릴 수 없다.
        again = await command.upgrade(run_in_transaction=False)
        assert again == [], f"두 번째 upgrade 가 또 뭘 했다 — 배포가 굴러가지 않는다: {again}"
    finally:
        await Tortoise.close_connections()
        await _sql(None, f"DROP DATABASE IF EXISTS {SCRATCH}")


def test_the_guard_stands_before_the_drop_not_beside_it() -> None:
    """**막는 것과 우는 것은 다르다.**

    이름 확인이 별도 검사로 있으면 빨간불은 뜨지만 `DROP` 은 그대로 나간다.
    확인은 지우는 문장보다 **앞**에 있어야 하고, 같은 함수 안에 있어야 한다.

    글자를 세지 않고 **구문 나무**를 본다. 처음엔 글자로 셌더니 바로 위
    문서주석에 적어 둔 「`DROP DATABASE` 로 시작한다」는 설명을 제가 잡았다 —
    산문은 아무것도 지우지 않는다.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_make_scratch_database")

    # **문서주석을 먼저 들어낸다.** 그것도 `ast.Constant` 라서 그냥 걸으면
    # 「`DROP DATABASE` 로 시작한다」는 설명 문장을 지우는 문장으로 읽는다.
    # 글자로 세던 판이 딱 이 자리에서 틀렸고, 나무로 바꿔도 같은 자리를 밟았다.
    statements = fn.body[1:] if ast.get_docstring(fn) else fn.body
    nodes = [n for stmt in statements for n in ast.walk(stmt)]

    drops = [
        n.lineno
        for n in nodes
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "DROP DATABASE" in n.value
    ]
    guards = [
        n.lineno
        for n in nodes
        if isinstance(n, ast.Assert)
        and any(isinstance(a, ast.Attribute) and a.attr == "DB_NAME" for a in ast.walk(n.test))
    ]

    assert drops, "검사가 헛돈다 — 이 함수가 DROP 을 날리지 않는다"
    assert guards, "이름 확인이 이 함수 안에 없다 — 다른 검사로 빼 두면 울기만 하고 못 막는다"
    assert min(guards) < min(drops), (
        f"이름 확인({min(guards)}줄)이 DROP({min(drops)}줄) 뒤에 있다 — 울기만 하고 못 막는다"
    )


def test_this_file_refuses_to_be_skipped_on_ci() -> None:
    """**건너뛰기가 CI 까지 따라오면 안 된다.**

    위 `skip` 은 개발용 계정을 위한 것이다. 그 문이 CI 에서도 열려 있으면
    검사가 통째로 사라진 채 초록불이 뜬다 — 이 저장소에서 여러 번 본 모양이다.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    door = source[source.index("except OperationalError") :]

    assert "GITHUB_ACTIONS" in door[: door.index("pytest.skip")], (
        "건너뛰기 앞에 CI 확인이 없다 — CI 에서도 조용히 건너뛴다"
    )
