"""합성 직원 계정을 읽는다 — `docs/data/synthetic-staff.csv`.

KEY-10. 테스트가 계정을 코드에 박지 않고 정본 CSV 하나만 보게 한다.
CSV를 고치면 테스트가 따라 움직인다.

    from app.tests.fixtures.staff import STAFF, by_id, by_login

    by_id("SYN-STAFF-06")     # staff+admin — 의료 승인이 막혀야 하는 계정
    by_login("lock01")        # 5회 실패 잠금 전용

비밀번호는 여기 없다. 시드가 `SEED_STAFF_PASSWORD`에서 받아 넣는다
(`docs/synthetic-data-spec.md` 9절).
"""

import csv
from dataclasses import dataclass
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-staff.csv"

ROLE_SEPARATOR = "|"  # 쉼표는 CSV 구분자와 겹친다


@dataclass(frozen=True)
class Staff:
    scenario_id: str
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


def _load() -> tuple[Staff, ...]:
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        return tuple(
            Staff(
                scenario_id=r["시나리오ID"],
                login_id=r["login_id"],
                name=r["이름"],
                roles=frozenset(r["roles"].split(ROLE_SEPARATOR)),
                must_change_password=r["must_change_password"] == "Y",
                status=r["status"],
                left_at=r["left_at"],
                last_login_at=r["last_login_at"],
                intent=r["케이스의도"],
            )
            for r in csv.DictReader(f)
        )


STAFF: tuple[Staff, ...] = _load()


def by_id(scenario_id: str) -> Staff:
    for s in STAFF:
        if s.scenario_id == scenario_id:
            return s
    raise KeyError(f"그런 시나리오가 없다: {scenario_id}")


def by_login(login_id: str) -> Staff:
    for s in STAFF:
        if s.login_id == login_id:
            return s
    raise KeyError(f"그런 아이디가 없다: {login_id}")


def with_roles(*roles: str) -> Staff:
    """역할 조합이 정확히 일치하는 첫 계정. 재직 중인 사람만 고른다."""
    want = frozenset(roles)
    for s in STAFF:
        if s.roles == want and s.is_active and not s.must_change_password:
            return s
    raise KeyError(f"그 조합의 평범한 계정이 없다: {sorted(want)}")
