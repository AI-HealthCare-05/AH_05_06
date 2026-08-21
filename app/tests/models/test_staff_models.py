"""직원·병원 모델이 계약과 같은 모양인지 본다 — KEY-73.

계약은 `docs/api/hospital.md`(KEY-8 v1)와 기획의 `staff` 표다.
사람이 기억해서 지키는 대신 여기서 잡는다.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError, ValidationError

from app.models.staffs import Hospital, Staff, StaffRole, StaffStatus


async def make_hospital(name: str = "여성의원") -> Hospital:
    return await Hospital.create(name=name)


async def make_staff(hospital: Hospital, login_id: str, roles: list[str]) -> Staff:
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash="x" * 60,
        name="한소영",
        roles=roles,
    )


class TestStaffContract(TestCase):
    async def test_new_account_must_change_password(self) -> None:
        """관리자가 만든 계정은 첫 로그인에서 반드시 바꾼다(L-3).

        기본값이 False 면 임시 비밀번호가 그대로 계속 쓰인다.
        """
        hospital = await make_hospital()
        staff = await make_staff(hospital, "newbie01", ["staff"])

        assert staff.must_change_password is True
        assert staff.status is StaffStatus.ACTIVE
        assert staff.password_changed_at is None

    async def test_roles_overlap(self) -> None:
        """역할은 겹친다 — 실장은 계정도 만들고 접수도 한다."""
        hospital = await make_hospital()
        staff = await make_staff(hospital, "adminstaff1", ["admin", "staff"])

        assert staff.has_role(StaffRole.ADMIN)
        assert staff.has_role(StaffRole.STAFF)
        assert not staff.has_role(StaffRole.DOCTOR)

    async def test_empty_roles_are_refused(self) -> None:
        """빈 배열은 저장할 수 없다.

        아무 역할도 없는 계정은 로그인은 되는데 갈 곳이 없다 — 그 사실이
        로그인한 뒤에야 드러나면 「내 계정이 고장났나」로 읽힌다.
        """
        hospital = await make_hospital()

        with pytest.raises(ValidationError):
            await make_staff(hospital, "noroles01", [])

    async def test_unknown_role_is_refused(self) -> None:
        """오타로 만든 역할은 아무 권한도 안 주면서 있는 것처럼 보인다."""
        hospital = await make_hospital()

        with pytest.raises(ValidationError):
            await make_staff(hospital, "typo01", ["staff", "doctorr"])

    async def test_left_staff_keeps_roles_but_can_do_nothing(self) -> None:
        """그만둔 사람은 roles 가 남아 있어도 아무것도 못 한다.

        계정을 지우지 않는 것은 지난 기록이 이 이름을 가리키기 때문이다.
        """
        hospital = await make_hospital()
        staff = await make_staff(hospital, "left01", ["admin", "doctor", "staff"])

        staff.status = StaffStatus.LEFT
        await staff.save()

        assert staff.roles == ["admin", "doctor", "staff"]
        assert not staff.has_role(StaffRole.ADMIN)
        assert not staff.has_role(StaffRole.DOCTOR)
        assert not staff.has_role(StaffRole.STAFF)

    async def test_login_id_is_unique_across_hospitals(self) -> None:
        """아이디는 병원 안이 아니라 전체에서 유일하다.

        로그인은 병원을 알기 전에 일어난다. 두 병원에 같은 `staff01` 이 있으면
        비밀번호를 맞춘 사람이 누구인지 서버가 고를 수가 없다.
        """
        first = await make_hospital("여성의원")
        second = await make_hospital("옆동네의원")
        await make_staff(first, "staff01", ["staff"])

        with pytest.raises(IntegrityError):
            await make_staff(second, "staff01", ["staff"])

    async def test_hospital_is_a_real_relation(self) -> None:
        """환자·진료의 hospital_id 는 가리킬 테이블이 없었다(PR #25 리뷰).
        직원 쪽은 처음부터 실제 관계로 둔다 — 숫자만 있으면 병원 분리를
        코드가 지키는 수밖에 없다."""
        hospital = await make_hospital()
        staff = await make_staff(hospital, "staff02", ["staff"])

        await staff.fetch_related("hospital")
        assert staff.hospital.hospital_id == hospital.hospital_id

        listed = await hospital.staffs.all()
        assert [s.login_id for s in listed] == ["staff02"]


def load_migration() -> ModuleType:
    folder = Path(__file__).parents[2] / "core" / "db" / "migrations" / "models"
    path = next(folder.glob("*_add_hospital_staff.py"))
    spec = importlib.util.spec_from_file_location("hospital_staff_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration(TestCase):
    async def test_creates_parent_before_child_and_drops_child_first(self) -> None:
        """롤백은 자식부터 지워야 외래키에 안 걸린다.

        aerich 가 만든 순서는 hospital 을 먼저 지워서 롤백이 실패한다 —
        실제로 돌려 보고 잡은 것이라 순서를 검사로 못 박는다.
        """
        migration = load_migration()
        up = await migration.upgrade(None)
        down = await migration.downgrade(None)

        assert up.index("CREATE TABLE IF NOT EXISTS `hospital`") < up.index("CREATE TABLE IF NOT EXISTS `staff`")
        assert down.index("DROP TABLE IF EXISTS `staff`") < down.index("DROP TABLE IF EXISTS `hospital`")

    async def test_login_id_is_unique_in_schema(self) -> None:
        """유일성은 코드가 아니라 DB 가 지킨다 — 동시에 두 요청이 와도 막힌다."""
        migration = load_migration()
        up = await migration.upgrade(None)

        assert "`login_id` VARCHAR(50) NOT NULL UNIQUE" in up
        assert "REFERENCES `hospital` (`hospital_id`) ON DELETE RESTRICT" in up
