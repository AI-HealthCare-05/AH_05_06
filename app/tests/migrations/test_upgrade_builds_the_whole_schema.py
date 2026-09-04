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
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS, TORTOISE_ORM

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "app" / "core" / "db" / "migrations"

#: 이 검사만 쓰고 지우는 DB. 이름에 일감 번호를 박아 둔다 — 남의 DB 를 지우는
#: 사고가 나면 이름부터 눈에 띄어야 한다.
SCRATCH = "key206_upgrade_probe"


def _aerich(database: str, *args: str) -> subprocess.CompletedProcess[str]:
    """**딴 프로세스에서 `aerich` 를 돌린다** — 배포가 하는 것과 같은 꼴.

    처음에는 `aerich.Command` 를 이 프로세스에서 직접 불렀다. 로컬에서는
    권한이 없어 건너뛰어 몰랐는데, **CI 에서는 실제로 돌면서 뒤따르는 검사
    다섯을 깨뜨렸다.** `Command.init()` 이 전역 `Tortoise` 를 다른 설정으로
    다시 세우기 때문이다 — `use_tz` 와 `timezone: Asia/Seoul` 이 날아가서
    환자 OTP 검사들이 KST 를 UTC 로 읽고 만료를 오판했다.

        내 검사 빼고 전체        1406 passed
        내 검사 + patient_links     5 failed
        patient_links 만           42 passed

    별도 프로세스면 그 오염이 원천적으로 없다. **그리고 배포가 실제로 이
    꼴로 돈다** — `docker compose run … aerich upgrade`. 재는 것이 실물에
    가까워진 것은 덤이 아니라 요점이다.
    """
    creds = TORTOISE_ORM["connections"]["default"]["credentials"]  # type: ignore[index]
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "DB_HOST": str(creds["host"]),
        "DB_PORT": str(creds["port"]),
        "DB_USER": str(creds["user"]),
        "DB_PASSWORD": str(creds["password"]),
        "DB_NAME": database,
        "SECRET_KEY": "synthetic-key206-not-a-secret",
        "ENV": "local",  # `Config` 는 local·dev·prod 만 받는다
    }
    return subprocess.run(
        [sys.executable, "-m", "aerich", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


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
    또 올린다」.
    """
    await _make_scratch_database()

    try:
        first = _aerich(SCRATCH, "upgrade")
        assert first.returncode == 0, f"빈 DB 에 upgrade 가 실패했다 — {first.stderr[-600:]}"
        assert "Success upgrading" in first.stdout, (
            f"적용된 마이그레이션이 없다 — upgrade 가 아무것도 안 했다: {first.stdout[-400:]}"
        )

        # ① 모델이 아는 표가 하나도 안 빠졌는가.
        #    「개수가 맞다」로는 부족하다 — 개수는 맞고 이름이 다를 수 있다.
        Tortoise.init_models(TORTOISE_APP_MODELS, "models")
        wanted = {d["table"] for d in Tortoise.describe_models(serializable=True).values()}
        built = {row[0] for row in await _sql(SCRATCH, "SHOW TABLES")}
        missing = sorted(wanted - built)
        assert not missing, f"모델은 아는데 upgrade 가 안 만든 표: {missing}"

        # ② 배포는 이걸 매번 돈다. 두 번째가 뭔가 한다면 굴릴 수 없다.
        again = _aerich(SCRATCH, "upgrade")
        assert again.returncode == 0, f"두 번째 upgrade 가 죽었다 — {again.stderr[-600:]}"
        assert "Success upgrading" not in again.stdout, (
            f"두 번째 upgrade 가 또 뭘 했다 — 배포가 굴러가지 않는다: {again.stdout[-400:]}"
        )
    finally:
        await _sql(None, f"DROP DATABASE IF EXISTS {SCRATCH}")


async def _one_session(database: str, statements: list[str]) -> list[Any]:
    """**한 연결에서** 여러 문장을 돌리고 커밋한다.

    `_sql` 은 문장마다 새 연결을 열고 커밋 없이 닫는다 — 읽기에는 맞지만
    넣은 것이 남지 않는다. 여기서는 넣고 그 값을 다시 봐야 한다.

    마지막 문장의 결과를 돌려준다. 문장이 죽으면 그대로 올린다 — 유니크가
    막는 것을 재는 것이 이 도구의 쓸모다.
    """
    import asyncmy  # type: ignore[import-untyped]

    creds = TORTOISE_ORM["connections"]["default"]["credentials"]  # type: ignore[index]
    conn = await asyncmy.connect(
        host=creds["host"],
        port=creds["port"],
        user=creds["user"],
        password=creds["password"],
        database=database,
        autocommit=True,
    )
    try:
        rows: list[Any] = []
        async with conn.cursor() as cur:
            for statement in statements:
                await cur.execute(statement)
                rows = list(await cur.fetchall())
        return rows
    finally:
        conn.close()


async def test_the_clinic_wide_wording_cannot_be_written_twice() -> None:
    """🚨 **`doctor_id` 가 비면 `unique_together` 가 안 먹는다.**

    37 번이 `doctor_id` 를 `NULL` 로 열면서 「의원 공통」을 만들었는데, MySQL
    에서 `NULL` 은 서로 같지 않다. 그래서 그 유니크가 **의원 공통 줄에
    대해서만 통째로 무력**해졌다 (`#192` 리뷰 ①, 2heej). 같은 처방의 문구가
    두 줄 생기면 `.first()` 가 아무거나 집어 **새로고침마다 글이 달라진다.**

    38 번이 `COALESCE(doctor_id, 0)` 로 「빈 것」을 하나로 접는 인덱스를
    얹었다. 그런데 **보통 검사로는 이걸 못 잰다** — 검사 DB 는 모델에서
    `generate_schemas()` 로 세워서 그 인덱스가 아예 없다. 마이그레이션을
    진짜로 돌리는 이 자리에서만 잴 수 있다.
    """
    await _make_scratch_database()

    try:
        done = _aerich(SCRATCH, "upgrade")
        assert done.returncode == 0, f"upgrade 가 실패했다 — {done.stderr[-400:]}"

        rows = await _one_session(
            SCRATCH,
            [
                "INSERT INTO prescription_set (name) VALUES ('검사용 세트')",
                "SELECT prescription_set_id FROM prescription_set LIMIT 1",
            ],
        )
        assert rows, "세트를 넣었는데 안 보인다 — 검사가 헛돈다"
        set_id = rows[0][0]

        common = (
            "INSERT INTO doctor_guide_copy "
            "(hospital_id, doctor_id, prescription_set_id, section_key, body) "
            f"VALUES (1, NULL, {set_id}, 'caution', '의원 공통')"
        )
        await _one_session(SCRATCH, [common])

        with pytest.raises(Exception) as clash:  # noqa: PT011 - 드라이버 예외형을 안 묶는다
            await _one_session(SCRATCH, [common])
        assert "Duplicate" in str(clash.value), (
            f"같은 (병원 · 빈 의사 · 세트 · 갈래) 가 두 줄 들어갔다 — 유니크가 안 먹는다: {clash.value}"
        )

        # 의사가 **찬** 줄은 서로 달라야 하니 막히면 안 된다.
        await _one_session(
            SCRATCH,
            [
                "INSERT INTO doctor_guide_copy "
                "(hospital_id, doctor_id, prescription_set_id, section_key, body) "
                f"VALUES (1, {doctor}, {set_id}, 'caution', '개인 문구')"
                for doctor in (11, 12)
            ],
        )
    finally:
        await _sql(None, f"DROP DATABASE IF EXISTS {SCRATCH}")


def test_the_migration_runs_in_its_own_process() -> None:
    """**이 검사가 남의 검사를 깨뜨리지 않게 한다.**

    한 프로세스 안에서 `aerich.Command` 를 부르면 전역 `Tortoise` 설정이
    갈린다. 로컬에서는 권한이 없어 건너뛰므로 **아무도 모른 채 CI 만 빨개진다** —
    실제로 그렇게 다섯이 깨졌다. 딴 프로세스로 도는지 못박아 둔다.
    """
    source = Path(__file__).read_text(encoding="utf-8")

    assert "subprocess.run" in source, "마이그레이션을 딴 프로세스에서 안 돌린다"

    # **낱말을 쪼개 둔다.** 통째로 적으면 이 줄 자신이 걸려서, 코드를 고쳐도
    # 검사가 계속 운다 — 이 저장소에서 여러 번 밟은 함정이라 여기서도 쪼갠다.
    in_process = "from aerich" + " import Command"
    assert in_process not in source, (
        "`aerich` 의 명령 객체를 이 프로세스에서 부른다 — 전역 Tortoise 설정이 갈려 뒤따르는 검사들이 깨진다"
    )


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
