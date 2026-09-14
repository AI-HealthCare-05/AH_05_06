"""직원을 **고칠 수 있다** — A1-3 (KEY-330).

어드민 화면이 직원을 보고 만들 수는 있었는데 고칠 수가 없었다. 그래서
그만둔 사람의 계정이 계속 살아 있었고, 비밀번호를 잊은 사람에게 줄 방법이
없었다.

여기서 재는 것은 셋이다.

  ① 역할·재직 상태·비밀번호를 **준 것만** 바꾼다
  ② 🚩 **관리자 없는 의원을 만들지 않는다**
  ③ 퇴사·비밀번호 재설정은 **그 사람을 로그아웃시킨다**

②가 이 파일의 무게중심이다. 화면에는 되돌릴 길이 없어서, 한 번 만들어지면
서버에 직접 넣거나 시드를 다시 돌려야 한다.
"""

from app.models.staffs import (
    Staff,
    StaffAccountEvent,
    StaffAccountEventType,
    StaffStatus,
)
from app.services.staff_auth import StaffSessionService
from app.tests.admin.test_key321_admin_staffs import AdminStaffTestCase
from app.tests.auth_base import PASSWORD, login_headers, make_staff_account

URL = "/api/v1/admin/staffs"
NEW_PASSWORD = "Synthetic-reset-9!"


class StaffEditTestCase(AdminStaffTestCase):
    async def patch(self, staff: Staff, body: dict, who: str = "admin01"):
        async with self.client() as client:
            return await client.patch(f"{URL}/{staff.staff_id}", headers=await login_headers(client, who), json=body)

    async def fresh(self, staff: Staff) -> Staff:
        return await Staff.get(staff_id=staff.staff_id)

    async def events(self, staff: Staff) -> list[str]:
        rows = await StaffAccountEvent.filter(subject_staff_id=staff.staff_id).order_by("staff_account_event_id")
        return [row.event_type for row in rows]


class TestItChangesOnlyWhatYouSend(StaffEditTestCase):
    async def test_roles_alone(self) -> None:
        answer = await self.patch(self.doctor, {"roles": ["doctor", "admin"]})

        assert answer.status_code == 200, answer.text
        again = await self.fresh(self.doctor)
        assert sorted(again.roles) == ["admin", "doctor"]
        assert StaffStatus(again.status) is StaffStatus.ACTIVE, "안 보낸 상태가 바뀌었다"
        assert not again.must_change_password, "안 보낸 비밀번호가 바뀌었다"

    async def test_status_alone(self) -> None:
        answer = await self.patch(self.doctor, {"status": "left"})

        assert answer.status_code == 200, answer.text
        again = await self.fresh(self.doctor)
        assert StaffStatus(again.status) is StaffStatus.LEFT
        assert again.left_at is not None, "언제 그만뒀는지가 안 남는다"
        assert sorted(again.roles) == ["doctor"], "안 보낸 역할이 바뀌었다"

    async def test_password_alone_forces_a_change_at_next_login(self) -> None:
        """관리자가 준 임시 비밀번호다 — 받은 사람이 **첫 로그인에서 바꾼다**(L-3)."""
        was = (await self.fresh(self.doctor)).password_hash

        answer = await self.patch(self.doctor, {"password": NEW_PASSWORD})

        assert answer.status_code == 200, answer.text
        again = await self.fresh(self.doctor)
        assert again.password_hash != was
        assert again.must_change_password is True

    async def test_nothing_to_change_is_refused(self) -> None:
        """「바꿀 것이 없는 저장」은 화면이 뭔가를 빠뜨렸다는 뜻이다.

        **`400 INVALID_REQUEST` 다.** 저장소의 `ContractRoute` 가 요청 형식
        잘못을 전부 그 코드로 모은다 — 여기만 `422` 를 내면 화면이 이 종점
        하나를 위해 분기를 더 만들어야 한다.
        """
        answer = await self.patch(self.doctor, {})

        assert answer.status_code == 400, answer.text
        assert answer.json()["code"] == "INVALID_REQUEST"

    async def test_a_combination_that_cannot_be_created_cannot_be_saved_either(self) -> None:
        """만들 수 없는 조합이 수정으로는 들어갈 수 있으면 그것은 규칙이 아니다."""
        answer = await self.patch(self.doctor, {"roles": ["doctor", "staff"]})

        assert answer.status_code == 400, answer.text
        assert answer.json()["code"] == "INVALID_ROLE_COMBINATION"
        assert sorted((await self.fresh(self.doctor)).roles) == ["doctor"]


class TestTheClinicNeverLosesItsLastAdmin(StaffEditTestCase):
    """🚩 **되돌릴 길이 화면에 없다.**

    관리자가 하나뿐인데 그 역할을 빼거나 퇴사시키면, 아무도 직원을 관리할 수
    없는 의원이 된다 — 서버에 직접 넣거나 시드를 다시 돌려야 한다.
    """

    async def test_taking_admin_off_the_last_one_is_refused(self) -> None:
        answer = await self.patch(self.admin, {"roles": ["staff"]})

        assert answer.status_code == 409, answer.text
        assert answer.json()["code"] == "LAST_ADMIN"
        assert sorted((await self.fresh(self.admin)).roles) == ["admin"], "막혔다면서 저장은 됐다"

    async def test_retiring_the_last_admin_is_refused(self) -> None:
        answer = await self.patch(self.admin, {"status": "left"})

        assert answer.status_code == 409, answer.text
        assert StaffStatus((await self.fresh(self.admin)).status) is StaffStatus.ACTIVE

    async def test_with_another_admin_it_goes_through(self) -> None:
        await make_staff_account(self.hospital, "admin02", ["admin"], name="다른관리자")

        answer = await self.patch(self.admin, {"roles": ["staff"]})

        assert answer.status_code == 200, answer.text
        assert sorted((await self.fresh(self.admin)).roles) == ["staff"]

    async def test_the_neighbour_clinics_admin_does_not_count(self) -> None:
        """**의원 단위 규칙이다.** 옆 의원에 관리자가 있다고 이 의원이
        관리자 없이 남아도 되는 것이 아니다."""
        assert self.other_admin.hospital_id != self.admin.hospital_id

        answer = await self.patch(self.admin, {"roles": ["staff"]})

        assert answer.status_code == 409, answer.text

    async def test_a_retired_admin_does_not_count_either(self) -> None:
        """그만둔 관리자는 아무것도 못 한다 — 있어도 없는 것이다."""
        spare = await make_staff_account(self.hospital, "admin03", ["admin"], name="그만둔관리자")
        await Staff.filter(staff_id=spare.staff_id).update(status=StaffStatus.LEFT)

        answer = await self.patch(self.admin, {"status": "left"})

        assert answer.status_code == 409, answer.text


class TestItLogsThemOut(StaffEditTestCase):
    """퇴사는 새 요청만 막는다 — **이미 발급된 액세스 토큰은 만료까지 산다.**
    그만둔 사람이 그동안 계속 쓴다."""

    async def signed_in(self, staff: Staff) -> None:
        await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]

    async def test_retiring_cuts_the_sessions(self) -> None:
        await self.signed_in(self.doctor)

        answer = await self.patch(self.doctor, {"status": "left"})

        assert answer.status_code == 200, answer.text
        assert answer.json()["revoked_sessions"] >= 1, "그만뒀는데 쓰던 세션이 살아 있다"

    async def test_resetting_the_password_cuts_them_too(self) -> None:
        await self.signed_in(self.doctor)

        answer = await self.patch(self.doctor, {"password": NEW_PASSWORD})

        assert answer.json()["revoked_sessions"] >= 1

    async def test_changing_only_roles_does_not(self) -> None:
        """굳이 끊으면 일하던 사람이 까닭 없이 튕긴다 — 다음 요청부터 새 역할로 판정된다."""
        await self.signed_in(self.doctor)

        answer = await self.patch(self.doctor, {"roles": ["doctor", "admin"]})

        assert answer.json()["revoked_sessions"] == 0


class TestTheFenceAndTheDoor(StaffEditTestCase):
    async def test_another_clinics_staff_is_not_found(self) -> None:
        """다른 의원 것은 **403 이 아니라 404** 다 — 있다는 사실도 알리지 않는다."""
        answer = await self.patch(self.other_admin, {"roles": ["staff"]})

        assert answer.status_code == 404, answer.text
        assert sorted((await self.fresh(self.other_admin)).roles) == ["admin"]

    async def test_a_doctor_cannot_edit_staff(self) -> None:
        answer = await self.patch(self.doctor, {"roles": ["staff"]}, who="doctor01")

        assert answer.status_code == 403, answer.text


class TestItLeavesATrail(StaffEditTestCase):
    async def test_each_change_gets_its_own_line(self) -> None:
        await self.patch(self.doctor, {"roles": ["doctor", "admin"], "status": "left", "password": NEW_PASSWORD})

        assert await self.events(self.doctor) == [
            StaffAccountEventType.STAFF_ROLES_CHANGED,
            StaffAccountEventType.STAFF_LEFT,
            StaffAccountEventType.STAFF_PASSWORD_RESET,
        ]

    async def test_coming_back_is_its_own_event(self) -> None:
        await self.patch(self.doctor, {"status": "left"})
        await self.patch(self.doctor, {"status": "active"})

        assert await self.events(self.doctor) == [
            StaffAccountEventType.STAFF_LEFT,
            StaffAccountEventType.STAFF_REINSTATED,
        ]
        assert (await self.fresh(self.doctor)).left_at is None, "돌아왔는데 그만둔 날짜가 남아 있다"

    async def test_no_password_ever_lands_in_the_trail(self) -> None:
        """**담을 칸 자체가 없다** — 그것이 담지 않겠다는 약속을 지키는 방법이다."""
        await self.patch(self.doctor, {"password": NEW_PASSWORD})

        rows = await StaffAccountEvent.filter(subject_staff_id=self.doctor.staff_id)
        written = " ".join(f"{row.event_type} {row.roles}" for row in rows)
        assert NEW_PASSWORD not in written
        assert PASSWORD not in written

    async def test_a_change_that_changes_nothing_leaves_no_line(self) -> None:
        """같은 값을 다시 보낸 것이다. 기록을 쌓으면 「누가 무엇을 바꿨나」가 흐려진다."""
        await self.patch(self.doctor, {"roles": ["doctor"], "status": "active"})

        assert await self.events(self.doctor) == []
