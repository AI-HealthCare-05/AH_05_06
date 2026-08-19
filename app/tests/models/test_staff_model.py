"""`Staff` 모델이 확정된 계약과 어긋나지 않는지 본다 — KEY-100.

필드 정의는 `docs/models-layout.md` 3장 ①, 로그인 계약은 `docs/auth-contract.md` 4·5절.
합성 계정은 `docs/data/synthetic-staff.csv` (KEY-10).
"""

import csv
from pathlib import Path

import pytest
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.users import Staff, StaffRole, StaffStatus

STAFF_CSV = Path(__file__).parents[3] / "docs" / "data" / "synthetic-staff.csv"
ROLE_SEPARATOR = "|"


@pytest.fixture(scope="module", autouse=True)
def initialize_models() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")


def test_staff_model_matches_frozen_contract() -> None:
    assert Staff._meta.db_table == "staff"
    assert Staff._meta.pk_attr == "staff_id"
    assert ("hospital_id", "status") in Staff._meta.indexes


def test_login_id_is_unique() -> None:
    """로그인 화면에 의원 선택이 없다 — `login_id` 하나로 사람이 정해져야 한다."""
    assert Staff._meta.fields_map["login_id"].unique is True


def test_staff_does_not_hold_personal_information() -> None:
    """직원 개인정보는 들지 않는다 — `docs/models-layout.md` 3장 ①."""
    for field in ("gender", "birthday", "birth_date", "phone_number", "phone", "email"):
        assert field not in Staff._meta.fields_map


def test_roles_allow_multiple_selection() -> None:
    """관리자 + 스탭처럼 겹치는 역할이 정상이다 (`A1-2` 체크박스 셋)."""
    assert set(StaffRole) == {StaffRole.STAFF, StaffRole.DOCTOR, StaffRole.ADMIN}
    staff = Staff(roles=[StaffRole.STAFF, StaffRole.ADMIN])
    assert staff.has_role(StaffRole.ADMIN) is True
    assert staff.has_role(StaffRole.DOCTOR) is False


def test_leaver_is_kept_as_status_not_deleted() -> None:
    """퇴사자는 지우지 않는다 — 지난 기록이 이름을 참조한다."""
    assert set(StaffStatus) == {StaffStatus.ACTIVE, StaffStatus.LEFT}
    assert Staff._meta.fields_map["status"].default is StaffStatus.ACTIVE
    assert Staff._meta.fields_map["left_at"].null is True
    assert Staff(status=StaffStatus.LEFT).is_active is False


def test_must_change_password_defaults_to_true() -> None:
    """어드민이 만든 첫 비밀번호는 본인이 바꾼다 — `L-3` 화면의 근거."""
    assert Staff._meta.fields_map["must_change_password"].default is True


def test_migration_sql_matches_model() -> None:
    source = (
        Path(__file__).parents[2] / "core" / "db" / "migrations" / "models" / "2_20260819173149_add_staff.py"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS `staff`" in source
    assert "`login_id` VARCHAR(50) NOT NULL UNIQUE" in source
    assert "DROP TABLE IF EXISTS `staff`" in source


@pytest.mark.skipif(not STAFF_CSV.exists(), reason="synthetic-staff.csv 는 KEY-10(PR #12) 병합 후 들어온다")
def test_fixture_values_fit_the_model() -> None:
    """합성 계정 14개의 roles·status 가 모델 enum 안에 있는지 본다."""
    with STAFF_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows
    for row in rows:
        assert row["status"] in {s.value for s in StaffStatus}
        for role in row["roles"].split(ROLE_SEPARATOR):
            assert role in {r.value for r in StaffRole}
        assert row["must_change_password"] in {"Y", "N"}
        assert len(row["login_id"]) <= 50
