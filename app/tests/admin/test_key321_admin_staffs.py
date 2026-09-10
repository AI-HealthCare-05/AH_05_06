"""어드민이 직원을 보고 만든다 — A1-1 · A1-2 (KEY-321).

`Staff` 모델과 역할 조합은 이미 있었는데 **읽고 쓰는 길이 없었다.** 그래서
`admin.html` 이 골격만이었다(KEY-176). 여기서 재는 것은 길이 생겼다는 사실이
아니라 **그 길이 무엇을 막는가**다.

    병원 울타리   남의 의원 직원이 목록에 안 나오고, 남의 의원에 못 만든다
    역할 조합     계약에 없는 조합(`staff|doctor`)은 400
    비밀번호      원문이 응답·목록·감사 기록 어디에도 안 남는다
    감사 기록     계정을 만들면 반드시 한 줄이 남고, 실패하면 안 남는다
"""

from typing import Any

from httpx import ASGITransport, AsyncClient

from app.core.utils.security import verify_password
from app.main import app
from app.models.staffs import Hospital, Staff, StaffAccountEvent, StaffAccountEventType, StaffStatus
from app.tests.auth_base import PASSWORD, AuthTestCase, login_headers, make_staff_account

STAFFS_URL = "/api/v1/admin/staffs"

#: 만들 계정에 줄 첫 비밀번호. 계약의 「영문 · 숫자 · 기호를 섞어 8자 이상」을 지킨다.
NEW_PASSWORD = "Synthetic-new-1!"


def _body(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "login_id": "newstaff01",
        "name": "새직원",
        "password": NEW_PASSWORD,
        "roles": ["staff"],
    }
    payload.update(over)
    return payload


class AdminStaffTestCase(AuthTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.hospital = await Hospital.create(name="도로시여성의원")
        self.other = await Hospital.create(name="옆집여성의원")
        self.admin = await make_staff_account(self.hospital, "admin01", ["admin"], name="관리자")
        self.doctor = await make_staff_account(self.hospital, "doctor01", ["doctor"], name="박연")
        self.other_admin = await make_staff_account(self.other, "admin21", ["admin"], name="옆집관리자")

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestOnlyAdminsGetThroughTheDoor(AdminStaffTestCase):
    async def test_an_admin_sees_the_list(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.get(STAFFS_URL, headers=headers)

        assert response.status_code == 200, response.text

    async def test_a_doctor_is_refused(self) -> None:
        """**의사는 진료를 하지 계정을 만들지 않는다.** `admin` 만 지난다.

        403 이지 404 가 아니다 — 없는 척하면 관리자가 「내 권한이 없구나」
        대신 「기능이 없구나」로 읽는다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "doctor01")
            listed = await client.get(STAFFS_URL, headers=headers)
            made = await client.post(STAFFS_URL, json=_body(), headers=headers)

        assert listed.status_code == 403, listed.text
        assert made.status_code == 403, made.text
        assert await Staff.filter(login_id="newstaff01").count() == 0, "막혔는데 계정이 생겼다"

    async def test_nobody_gets_in_without_a_token(self) -> None:
        async with self.client() as client:
            listed = await client.get(STAFFS_URL)
            made = await client.post(STAFFS_URL, json=_body())

        assert listed.status_code == 401, listed.text
        assert made.status_code == 401, made.text


class TestTheHospitalFenceHolds(AdminStaffTestCase):
    async def test_the_list_only_has_my_clinic(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.get(STAFFS_URL, headers=headers)

        ids = [row["login_id"] for row in response.json()["staffs"]]
        assert ids == ["admin01", "doctor01"], ids
        assert "admin21" not in ids, "옆집 의원 직원이 목록에 있다"

    async def test_a_new_account_lands_in_my_clinic(self) -> None:
        """**병원을 요청에서 안 받는다.** 토큰이 가리키는 계정에서만 온다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(), headers=headers)

        assert response.status_code == 201, response.text
        made = await Staff.get(login_id="newstaff01")
        assert made.hospital_id == self.hospital.hospital_id

    async def test_the_request_cannot_choose_the_clinic(self) -> None:
        """남의 의원 번호를 실어 보내도 **거절된다** — `extra="forbid"` 다.

        조용히 무시하면 보낸 사람은 그 값이 쓰였다고 믿는다.

        형식 오류는 이 저장소에서 **400 `INVALID_REQUEST`** 다 — `ContractRoute`
        가 FastAPI 의 422 를 계약 모양으로 옮긴다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(hospital_id=self.other.hospital_id), headers=headers)

        assert response.status_code == 400, response.text
        assert response.json()["code"] == "INVALID_REQUEST"
        assert [e["field"] for e in response.json()["field_errors"]] == ["hospital_id"]
        assert await Staff.filter(login_id="newstaff01").count() == 0


class TestOneBadRowDoesNotBlindTheWholeList(AdminStaffTestCase):
    """**한 줄이 이상해도 목록은 계속 쓸 수 있어야 한다** (한금준 님 `#285` 리뷰 ①).

    처음에는 목록이 저장된 역할을 `StaffRole(...)` 로 옮겼다. `roles` JSON 에
    아는 값 밖의 것이 하나라도 있으면 `ValueError` → **엔드포인트 전체가 500**
    이고, 관리자는 그 의원의 **아무 직원도** 못 본다. 하필 그 값을 고쳐야 하는
    사람이 못 보는 것이다.

    `Staff.save()` 가 역할을 검사하지만 그것을 안 지나는 길이 있다 — 레거시
    데이터 · 백필 마이그레이션 · raw insert · `bulk_create`.
    """

    async def _plant_a_bad_role(self) -> None:
        """모델을 거치지 않고 표를 직접 고친다 — `save()` 검증을 지나지 않는
        길을 흉내내는 것이 요점이다."""
        await Staff.filter(login_id="doctor01").update(roles=["doctor", "예전에쓰던역할"])

    async def test_the_list_still_answers(self) -> None:
        await self._plant_a_bad_role()

        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.get(STAFFS_URL, headers=headers)

        assert response.status_code == 200, f"한 줄 때문에 목록 전체가 막힌다 — {response.text[:200]}"
        assert len(response.json()["staffs"]) == 2, "줄이 사라졌다"

    async def test_the_odd_value_is_shown_not_hidden(self) -> None:
        """**건너뛰지 않고 보인다.** 감추면 그것을 고칠 사람이 그 사실을 모른다."""
        await self._plant_a_bad_role()

        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.get(STAFFS_URL, headers=headers)

        found = next(row for row in response.json()["staffs"] if row["login_id"] == "doctor01")
        assert found["roles"] == ["doctor", "예전에쓰던역할"], found["roles"]

    async def test_making_an_account_is_still_strict(self) -> None:
        """**들어오는 문은 그대로 좁다.** 읽을 때 너그러운 것이 쓸 때까지
        너그러워지면 이 티켓이 세운 관문이 없어진다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(roles=["예전에쓰던역할"]), headers=headers)

        assert response.status_code == 400, response.text
        assert await Staff.filter(login_id="newstaff01").count() == 0


class TestTheRoleCombinationRuleIsEnforced(AdminStaffTestCase):
    async def test_staff_and_doctor_together_are_refused(self) -> None:
        """계약에 없는 조합이다 — `staff` ⊂ `doctor` 라 `doctor` 와 권한이 같다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(roles=["staff", "doctor"]), headers=headers)

        assert response.status_code == 400, response.text
        assert response.json()["code"] == "INVALID_ROLE_COMBINATION"
        assert await Staff.filter(login_id="newstaff01").count() == 0

        #: **오류 봉투가 저장소 모양이어야 한다** — `list[{field, message}]`.
        #: 여기만 dict 였고, 그것을 리스트로 순회하는 쪽이 이 400 에서 터졌다
        #: (한금준 님 `#285` 리뷰 ②).
        errors = response.json()["field_errors"]
        assert isinstance(errors, list), f"field_errors 가 리스트가 아니다 — {errors}"
        assert [one["field"] for one in errors] == ["roles"], errors
        assert errors[0]["message"], "무엇이 잘못됐는지 안 말한다"

    async def test_the_admin_overlays_are_allowed(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            first = await client.post(
                STAFFS_URL, json=_body(login_id="deskchief1", roles=["staff", "admin"]), headers=headers
            )
            second = await client.post(
                STAFFS_URL, json=_body(login_id="owner0001", roles=["doctor", "admin"]), headers=headers
            )

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

    async def test_an_unknown_role_never_becomes_an_account(self) -> None:
        """모르는 값을 버리고 남은 것으로 만들면 고른 것과 저장된 것이 갈린다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(roles=["admin", "typo"]), headers=headers)

        assert response.status_code == 400, response.text
        assert await Staff.filter(login_id="newstaff01").count() == 0


class TestTheInitialPasswordNeverLeaks(AdminStaffTestCase):
    async def test_the_response_does_not_echo_it(self) -> None:
        """관리자가 방금 적은 값이라 화면이 이미 안다. 실으면 한 겹 더 남는다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(), headers=headers)

        assert response.status_code == 201, response.text
        assert NEW_PASSWORD not in response.text, "응답에 초기 비밀번호 원문이 있다"
        assert "password" not in response.json(), f"응답에 비밀번호 칸이 있다: {sorted(response.json())}"

    async def test_the_list_does_not_carry_it(self) -> None:
        """해시도 안 내보낸다 — 화면이 안 쓰는 값을 계약에 담지 않는다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.post(STAFFS_URL, json=_body(), headers=headers)
            listed = await client.get(STAFFS_URL, headers=headers)

        assert NEW_PASSWORD not in listed.text, "목록에 초기 비밀번호 원문이 있다"
        assert "password_hash" not in listed.text, "목록이 해시를 내보낸다"

    async def test_the_audit_row_does_not_carry_it(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.post(STAFFS_URL, json=_body(), headers=headers)

        event = await StaffAccountEvent.get(subject_staff__login_id="newstaff01")
        stored = {name: getattr(event, name) for name in event._meta.fields_map if hasattr(event, name)}
        assert NEW_PASSWORD not in str(stored), f"감사 기록에 초기 비밀번호가 있다: {stored}"

    async def test_it_is_stored_hashed_and_actually_works(self) -> None:
        """**해시로 저장되고, 그 해시가 진짜 그 비밀번호다.**

        「원문이 아니다」만 재면 아무 문자열이나 넣어도 통과한다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.post(STAFFS_URL, json=_body(), headers=headers)

        made = await Staff.get(login_id="newstaff01")
        assert made.password_hash != NEW_PASSWORD, "비밀번호가 원문으로 저장됐다"
        assert verify_password(NEW_PASSWORD, made.password_hash), "저장된 해시가 그 비밀번호가 아니다"


class TestTheAuditRowIsWrittenWithTheAccount(AdminStaffTestCase):
    async def test_one_row_per_created_account(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(roles=["doctor"]), headers=headers)

        made = await Staff.get(login_id="newstaff01")
        events = await StaffAccountEvent.filter(subject_staff_id=made.staff_id)
        assert len(events) == 1, f"감사 기록이 {len(events)} 줄이다"
        event = events[0]
        assert event.event_type is StaffAccountEventType.STAFF_CREATED
        assert event.actor_staff_id == self.admin.staff_id, "누가 만들었는지가 안 남았다"
        assert event.hospital_id == self.hospital.hospital_id
        assert event.roles == ["doctor"], "그때 준 역할이 안 남았다"
        assert response.json()["staff_id"] == made.staff_id

    async def test_a_refused_request_leaves_nothing_behind(self) -> None:
        """**계정과 기록은 한 트랜잭션이다.** 실패하면 둘 다 없어야 한다."""
        before = await StaffAccountEvent.all().count()

        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.post(STAFFS_URL, json=_body(roles=["staff", "doctor"]), headers=headers)

        assert await StaffAccountEvent.all().count() == before, "거절된 요청이 감사 기록을 남겼다"

    async def test_a_duplicate_login_id_leaves_nothing_behind(self) -> None:
        before = await StaffAccountEvent.all().count()

        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            response = await client.post(STAFFS_URL, json=_body(login_id="doctor01"), headers=headers)

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "LOGIN_ID_TAKEN"
        assert await StaffAccountEvent.all().count() == before


class TestTheNewAccountCanActuallyBeUsed(AdminStaffTestCase):
    async def test_it_logs_in_and_must_change_the_password_first(self) -> None:
        """인수조건 — **만든 계정으로 즉시 로그인된다.**

        그리고 첫 로그인에서 비밀번호를 바꿔야 한다(L-3). 관리자가 정해 준
        비밀번호를 그대로 쓰면 정해 준 사람이 그것을 계속 안다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            created = await client.post(STAFFS_URL, json=_body(), headers=headers)
            assert created.json()["must_change_password"] is True

            login = await client.post("/api/v1/auth/login", json={"login_id": "newstaff01", "password": NEW_PASSWORD})

        assert login.status_code == 200, login.text
        assert login.json()["must_change_password"] is True, "첫 로그인인데 안 바꿔도 된다고 한다"

    async def test_the_given_roles_decide_what_it_can_reach(self) -> None:
        """인수조건 — **부여한 역할 조합대로 화면 접근이 갈린다.**

        비밀번호 관문을 지난 뒤에 잰다. 관문에 막혀 403 이 나면 「역할 때문에
        막혔다」와 구별이 안 된다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.post(STAFFS_URL, json=_body(login_id="plainstaff", roles=["staff"]), headers=headers)

            await Staff.filter(login_id="plainstaff").update(must_change_password=False)
            staff_headers = await login_headers(client, "plainstaff", NEW_PASSWORD)
            refused = await client.get(STAFFS_URL, headers=staff_headers)

        assert refused.status_code == 403, "스탭으로 만들었는데 어드민 API 가 열린다"

    async def test_a_created_account_is_active(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.post(STAFFS_URL, json=_body(), headers=headers)

        made = await Staff.get(login_id="newstaff01")
        assert made.status is StaffStatus.ACTIVE


class TestTheLoginIdRuleIsCheckedHere(AdminStaffTestCase):
    """계약 2절이 「형식 검사는 계정을 만들 때 한다」로 미뤄 둔 자리다.

    로그인은 일부러 형식을 안 본다 — 규칙에 안 맞는 문자열이 「없는 아이디」와
    다른 답을 받으면 계정 존재 여부가 샌다.
    """

    async def test_a_bad_login_id_is_refused(self) -> None:
        for bad in ["abc", "Admin01", "admin 01", "관리자01", "admin-01", ""]:
            async with self.client() as client:
                headers = await login_headers(client, "admin01")
                response = await client.post(STAFFS_URL, json=_body(login_id=bad), headers=headers)

            assert response.status_code == 400, f"{bad!r} 이 통과했다 — {response.text}"

    async def test_a_weak_password_is_refused(self) -> None:
        for weak in ["short1!", "onlyletters!", "12345678!", "noSymbol123"]:
            async with self.client() as client:
                headers = await login_headers(client, "admin01")
                response = await client.post(STAFFS_URL, json=_body(password=weak), headers=headers)

            assert response.status_code == 400, f"{weak!r} 이 통과했다 — {response.text}"
        assert await Staff.filter(login_id="newstaff01").count() == 0

    async def test_the_seeded_password_still_logs_in(self) -> None:
        """이 파일이 쓰는 합성 비밀번호가 규칙을 지키는지 — 검사가 헛돌지 않게."""
        async with self.client() as client:
            response = await client.post("/api/v1/auth/login", json={"login_id": "admin01", "password": PASSWORD})
        assert response.status_code == 200, response.text
