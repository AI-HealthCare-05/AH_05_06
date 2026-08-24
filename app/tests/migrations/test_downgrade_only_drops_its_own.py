"""마이그레이션이 **자기가 만든 표만** 지우는지 본다 — KEY-111 (`#50` 리뷰).

여기 있는 이유가 요점이다.

`KEY-111` 의 첫 마이그레이션은 빈 DB 에서 `aerich migrate` 를 돌린 탓에 모델
전체 상태를 담았다. 그래서 안내문 표 셋만이 아니라 `visit` · `patient` ·
`ocr_*` 까지 만들고, **`downgrade()` 가 그것들을 통째로 지웠다.** 1~6번이
만든 표를 8번이 지우는 꼴이라, 되돌리는 순간 진료 데이터가 날아간다.

검사가 못 잡았다. 마이그레이션은 테스트가 부르지 않고, 테스트 DB 는
`generate_schemas()` 로 모델에서 바로 만들어지기 때문이다. **되돌리기는
아무도 안 해 보는 자리다.**

표 이름을 박아 두지 않는다. 그러면 표가 늘 때마다 이 파일을 고쳐야 하고,
고치는 걸 잊으면 검사가 조용히 헐거워진다. 규칙 자체를 적는다 —
**한 마이그레이션의 `downgrade` 는 그 `upgrade` 가 만든 표만 지운다.**
"""

import re

from app.tests.migrations.conftest import migration_files

_CREATE = re.compile(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+`([a-z_]+)`", re.I)
_DROP = re.compile(r"DROP TABLE(?:\s+IF EXISTS)?\s+`([a-z_]+)`", re.I)


def _body(text: str, func: str) -> str:
    """`async def <func>` 부터 다음 최상위 정의 전까지."""
    start = text.index(f"async def {func}")
    rest = text[start:]
    for marker in ("\nasync def ", "\nMODELS_STATE", "\ndef "):
        cut = rest.find(marker, 1)
        if cut != -1:
            rest = rest[:cut]
    return rest


def test_downgrade_never_drops_a_table_it_did_not_create() -> None:
    offenders: list[str] = []
    for path in migration_files():
        text = path.read_text(encoding="utf-8")
        created = set(_CREATE.findall(_body(text, "upgrade")))
        dropped = set(_DROP.findall(_body(text, "downgrade")))
        stray = dropped - created
        if stray:
            offenders.append(f"{path.name} → {sorted(stray)}")

    assert not offenders, (
        "마이그레이션이 자기가 만들지 않은 표를 지운다. 되돌리면 남의 데이터가 사라진다 — " + " · ".join(offenders)
    )


def test_children_are_dropped_before_their_parents() -> None:
    """FK 로 물린 표는 자식부터 지워야 한다.

    처음 만든 순서는 부모가 먼저라 `errno 3730` 으로 멈췄다. 중간에 멈추면
    반쯤 지워진 DB 가 남는다.
    """
    offenders: list[str] = []
    for path in migration_files():
        text = path.read_text(encoding="utf-8")
        up = _body(text, "upgrade")
        order = _DROP.findall(_body(text, "downgrade"))
        position = {name: i for i, name in enumerate(order)}
        for child, parent in re.findall(
            r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+`([a-z_]+)`.*?REFERENCES\s+`([a-z_]+)`", up, re.S | re.I
        ):
            if child in position and parent in position and position[child] > position[parent]:
                offenders.append(f"{path.name}: `{parent}` 를 `{child}` 보다 먼저 지운다")

    assert not offenders, "부모를 자식보다 먼저 지운다 — " + " · ".join(offenders)


def test_no_migration_recreates_a_table_an_earlier_one_owns() -> None:
    """앞선 마이그레이션이 이미 만든 표를 다시 만들지 않는다.

    **이것이 실제로 깨졌던 규칙이다.** `downgrade` 만 보면 안 걸린다 —
    문제의 파일은 `visit` · `patient` · `ocr_*` 를 만들기도 하고 지우기도 해서
    「자기가 만든 것만 지운다」는 통과했다. 그런데 그 표들의 주인은 1~6번이다.
    주인이 둘이면 되돌릴 때 누구 것을 지우는지 알 수 없다.

    `CREATE TABLE IF NOT EXISTS` 라 올릴 때는 조용하다. 내릴 때 터진다.
    """
    owner: dict[str, str] = {}
    offenders: list[str] = []
    for path in migration_files():
        up = _body(path.read_text(encoding="utf-8"), "upgrade")
        for table in _CREATE.findall(up):
            if table in owner:
                offenders.append(f"`{table}` — {owner[table]} 가 만든 것을 {path.name} 가 또 만든다")
            else:
                owner[table] = path.name

    assert not offenders, (
        "표를 두 마이그레이션이 만든다. 빈 DB 에서 `aerich migrate` 를 돌리면 이렇게 된다 — " + " · ".join(offenders)
    )


def test_the_guard_actually_reads_something() -> None:
    """통과하는 이유가 「파일을 못 읽어서」면 안 된다."""
    files = migration_files()
    assert len(files) >= 9, f"마이그레이션을 {len(files)}개만 찾았다"
    created = {t for p in files for t in _CREATE.findall(_body(p.read_text(encoding="utf-8"), "upgrade"))}
    assert {"visit", "patient", "guide_document"} <= created, f"표를 제대로 못 읽었다: {sorted(created)}"
