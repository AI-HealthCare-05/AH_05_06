"""합성 직원 계정을 읽는다 — `docs/data/synthetic-staff.csv`.

KEY-10. 테스트가 계정을 코드에 박지 않고 정본 CSV 하나만 보게 한다.
CSV를 고치면 테스트가 따라 움직인다.

    from app.tests.fixtures.staff import all_staff, by_id, by_login, with_roles

    by_id("SYN-STAFF-06")     # staff+admin — 의료 승인이 막혀야 하는 계정
    by_login("lock01")        # 5회 실패 잠금 전용
    with_roles("doctor")      # 그 조합의 **평범한** 계정 하나

비밀번호는 여기 없다. 시드가 `SEED_STAFF_PASSWORD`에서 받아 넣는다
(`docs/synthetic-data-spec.md` 9절).
"""

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-staff.csv"

ROLE_SEPARATOR = "|"  # 쉼표는 CSV 구분자와 겹친다

COLUMNS = (
    "시나리오ID",
    "병원",
    "login_id",
    "이름",
    "roles",
    "must_change_password",
    "status",
    "left_at",
    "last_login_at",
    "케이스의도",
)

KNOWN_STATUSES = frozenset({"active", "left"})
YES_NO = frozenset({"Y", "N"})

#: 의원 둘. 실제 `hospital_id` 는 bigint 라 DB 가 넣을 때 발급한다 —
#: 여기서는 어느 의원 소속인지만 표시한다.
#:
#:   H1  기준 의원. 환자 CSV 도 전부 여기다
#:   H2  격리 확인용. **H1 자료가 보이면 안 되는** 쪽
#:
#: 병원 격리는 이 서비스에서 제일 중요한 경계인데(`patient-visit-api-v1.md` 5절)
#: 의원이 하나뿐이면 「타 병원 404」를 검사할 상대가 없다.
KNOWN_HOSPITALS = frozenset({"H1", "H2"})

#: 병원을 말하지 않은 검사가 뜻하는 곳. 기존 시나리오는 전부 여기 있다.
DEFAULT_HOSPITAL = "H1"

#: 이름을 대고 불러야만 오는 계정.
#:
#: `with_roles()` 는 이 계정을 절대 집지 않는다. 어떤 시험이 우연히 집어 가면
#: 그 계정이 노리는 상황 자체가 무너지기 때문이다.
#:
#:   lock01       로그인 실패 횟수가 **입력된 아이디 문자열**에 붙는다
#:                (`docs/auth-contract.md` 3절). 다른 시험이 같이 쓰면
#:                순서에 따라 결과가 달라진다.
#:   lastadmin01  「마지막 관리자」 시나리오 전용. 다른 시험이 이 계정으로
#:                평범한 admin 일을 하면 그 시나리오가 성립하지 않는다.
RESERVED_LOGIN_IDS = frozenset({"lock01", "lastadmin01"})


class StaffDataError(ValueError):
    """CSV 가 앞뒤가 안 맞을 때. 무엇이 어디서 틀렸는지 적어 준다."""


@dataclass(frozen=True)
class Staff:
    scenario_id: str
    hospital: str
    login_id: str
    name: str
    roles: frozenset[str]
    must_change_password: bool
    status: str
    left_at: str
    last_login_at: str
    intent: str

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_reserved(self) -> bool:
        return self.login_id in RESERVED_LOGIN_IDS

    @property
    def is_ordinary(self) -> bool:
        """다른 이유로 막히지 않는 계정.

        재직 중이고 첫 로그인이 아니다. 어떤 시험이 「역할 때문에 막힌다」를
        보려면 그 계정이 **다른 이유로는 안 막혀야** 한다 — 안 그러면
        무엇 때문에 막혔는지 알 수 없다.
        """
        return self.is_active and not self.must_change_password


def _row_to_staff(line: int, row: dict[str | None, str | list[str] | None]) -> Staff:
    # DictReader 는 칸이 남으면 None 키에 몰아넣는다. 케이스 의도에 쉼표를
    # 따옴표 없이 쓰면 그 행부터 칸이 밀리는데, 값이 그럴듯해서 안 보인다.
    if row.get(None) is not None:
        raise StaffDataError(f"{line}행: 칸이 {len(COLUMNS)}개를 넘는다 — 쉼표가 든 값은 따옴표로 감싼다")

    missing = [c for c in COLUMNS if row.get(c) is None]
    if missing:
        raise StaffDataError(f"{line}행: 빠진 칸 {missing}")

    def text(column: str) -> str:
        value = row[column]
        return value.strip() if isinstance(value, str) else ""

    flag = text("must_change_password")
    if flag not in YES_NO:
        # "y" 나 "true" 가 오면 조용히 False 로 읽혀서, 첫 로그인 계정이
        # 평범한 계정이 된다 — L-3 시험이 아무것도 안 보고 통과한다.
        raise StaffDataError(f"{line}행: must_change_password 는 Y 나 N 이어야 한다 (받은 값 {flag!r})")

    hospital = text("병원")
    if hospital not in KNOWN_HOSPITALS:
        # 오타가 나면 그 계정이 어느 의원에도 안 붙어서, 격리 검사가
        # 「안 보인다」를 통과시킨다 — 격리가 되는지 안 되는지 알 수 없다.
        raise StaffDataError(f"{line}행: 병원 은 {sorted(KNOWN_HOSPITALS)} 중 하나여야 한다 (받은 값 {hospital!r})")

    status = text("status")
    if status not in KNOWN_STATUSES:
        raise StaffDataError(f"{line}행: status 는 {sorted(KNOWN_STATUSES)} 중 하나여야 한다 (받은 값 {status!r})")

    return Staff(
        scenario_id=text("시나리오ID"),
        hospital=hospital,
        login_id=text("login_id"),
        name=text("이름"),
        roles=frozenset(text("roles").split(ROLE_SEPARATOR)),
        must_change_password=flag == "Y",
        status=status,
        left_at=text("left_at"),
        last_login_at=text("last_login_at"),
        intent=text("케이스의도"),
    )


@cache
def all_staff() -> tuple[Staff, ...]:
    """CSV 를 읽는다. **부를 때** 읽는다.

    예전에는 import 시점에 읽었다. 그러면 CSV 가 깨졌을 때 이 파일뿐 아니라
    이걸 import 하는 다른 검사까지 수집 단계에서 통째로 죽어서, 실패 목록에
    「무엇이 틀렸는지」가 안 남는다.
    """
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        return tuple(_row_to_staff(i, dict(r)) for i, r in enumerate(csv.DictReader(f), start=2))


def by_id(scenario_id: str) -> Staff:
    for s in all_staff():
        if s.scenario_id == scenario_id:
            return s
    raise KeyError(f"그런 시나리오가 없다: {scenario_id}")


def by_login(login_id: str) -> Staff:
    for s in all_staff():
        if s.login_id == login_id:
            return s
    raise KeyError(f"그런 아이디가 없다: {login_id}")


def in_hospital(hospital: str) -> tuple[Staff, ...]:
    """그 의원 사람들.

    격리 검사는 **양쪽이 다 있어야** 성립한다 — 한쪽만 있으면 「안 보인다」가
    격리 때문인지 자료가 없어서인지 구분되지 않는다.
    """
    if hospital not in KNOWN_HOSPITALS:
        raise KeyError(f"그런 의원이 없다: {hospital}")
    return tuple(s for s in all_staff() if s.hospital == hospital)


def with_roles(*roles: str, hospital: str = DEFAULT_HOSPITAL) -> Staff:
    """그 의원에서 역할 조합이 정확히 일치하는 **평범한** 계정 하나.

    예약 계정은 건너뛴다. 예전에는 `lock01` 이 목록 뒤쪽에 있어서 우연히
    안 걸렸을 뿐이라, 앞 행이 바뀌면 조용히 집혀 왔다.

    의원을 안 적으면 기준 의원(`H1`)에서 찾는다. 대부분의 검사는 의원이
    하나라고 여기고 짜여 있고, 그 계정들이 전부 `H1` 이다.
    """
    want = frozenset(roles)
    for s in in_hospital(hospital):
        if s.roles == want and s.is_ordinary and not s.is_reserved:
            return s
    raise KeyError(f"{hospital} 에 그 조합의 평범한 계정이 없다: {sorted(want)}")


def admins_besides(login_id: str) -> tuple[Staff, ...]:
    """그 계정 말고 admin 을 가진 재직자들.

    「마지막 관리자」 시나리오는 **이 사람들이 없어야** 성립한다. 픽스처에는
    운영·겸직 admin 이 여럿 있어서, 그냥 `lastadmin01` 에서 admin 을 빼는
    저장은 아무 규칙에도 안 걸린다. 그 상태를 만들려면 무엇을 먼저 치워야
    하는지 여기서 내준다.

    **같은 의원 사람만 센다.** 「마지막 관리자」는 의원 단위 규칙이다 —
    옆 의원에 관리자가 있다고 이 의원이 관리자 없이 남아도 되는 것이 아니다.
    """
    who = by_login(login_id)
    return tuple(s for s in in_hospital(who.hospital) if "admin" in s.roles and s.is_active and s.login_id != login_id)
