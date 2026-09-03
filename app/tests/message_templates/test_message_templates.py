"""문자 문구 — KEY-234, 와이어프레임 D2-5 「★ 신설」.

원문 부제: 「문자 본문 템플릿 — 안내문(링크 콘텐츠)과 층이 다르다」. 환자
카드의 안내문 탭은 링크로 **열리는** 글을 다루고, 이 화면은 그 링크를 **실어
나르는** 문자 본문을 다룬다.

**두 가지를 가장 크게 잰다.**

  · 지울 수 없는 변수 — 링크가 빠진 확인 문자는 환자가 열 곳이 없다
  · 고치는 것은 의사만 — 원문 「문자도 환자에게 가는 안내다」
"""

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import MessageTemplate, MessageTemplateKind
from app.models.staffs import Hospital, Staff
from app.services.message_templates import (
    DEFAULT_BODY,
    SMS_LIMIT,
    sms_bytes,
    variables_in,
)
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis


class MessageTemplateTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_staff(self, roles: list[str], login: str, clinic: Hospital | None = None) -> Staff:
        clinic = clinic or await Hospital.create(name=f"의원 {login}")
        return await Staff.create(
            hospital=clinic,
            login_id=login,
            password_hash=hash_password("pw"),
            name="박연",
            roles=roles,
            must_change_password=False,
        )

    async def headers(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def fetch(self, staff: Staff) -> dict:
        async with self.client() as client:
            response = await client.get("/api/v1/message-templates", headers=await self.headers(staff))
        assert response.status_code == 200, response.text
        return response.json()

    async def save(self, staff: Staff, kind: MessageTemplateKind, body: str):
        async with self.client() as client:
            return await client.put(
                f"/api/v1/message-templates/{kind.value}",
                headers=await self.headers(staff),
                json={"body": body},
            )

    # ── 기본값 ───────────────────────────────────────────

    async def test_an_untouched_clinic_gets_the_defaults(self) -> None:
        """**줄이 없으면 기본 문구다.** 한 번도 안 고친 의원까지 미리 깔지 않는다."""
        staff = await self.a_staff(["doctor"], "fresh")

        body = await self.fetch(staff)

        assert len(body["items"]) == len(MessageTemplateKind)
        assert all(item["is_default"] for item in body["items"])
        for item in body["items"]:
            assert item["body"] == item["default_body"] == DEFAULT_BODY[MessageTemplateKind(item["kind"])]
        assert await MessageTemplate.all().count() == 0, "안 고쳤는데 줄이 생기면 안 된다"

    async def test_the_system_message_is_shown_but_not_stored(self) -> None:
        """원문 「인증번호 / 수정 불가 · 시스템」 — 무엇이 나가는지는 알아야 한다."""
        staff = await self.a_staff(["staff"], "sys")

        body = await self.fetch(staff)

        assert "인증번호" in body["system_body"]
        assert all(item["kind"] != "OTP" for item in body["items"]), "고칠 수 없는 것에 칸을 만들지 않는다"

    async def test_the_screen_learns_the_limit_and_the_variables(self) -> None:
        staff = await self.a_staff(["staff"], "meta")

        body = await self.fetch(staff)

        assert body["sms_limit"] == SMS_LIMIT == 90
        assert "링크" in body["known_variables"] and "예약링크" in body["known_variables"]

    # ── 저장 ─────────────────────────────────────────────

    async def test_a_doctor_saves_and_the_row_appears(self) -> None:
        staff = await self.a_staff(["doctor"], "save")

        response = await self.save(staff, MessageTemplateKind.CHECK_D7, "{환자명}님, 오늘 어떠세요? {링크}")

        assert response.status_code == 200
        saved = [row for row in response.json()["items"] if row["kind"] == "CHECK_D7"][0]
        assert saved["body"] == "{환자명}님, 오늘 어떠세요? {링크}"
        assert saved["is_default"] is False
        assert saved["default_body"] == DEFAULT_BODY[MessageTemplateKind.CHECK_D7], "되돌릴 곳을 화면이 알아야 한다"

    async def test_saving_twice_does_not_pile_up(self) -> None:
        staff = await self.a_staff(["doctor"], "twice")

        await self.save(staff, MessageTemplateKind.CHECK_D7, "{환자명}님 하나 {링크}")
        await self.save(staff, MessageTemplateKind.CHECK_D7, "{환자명}님 둘 {링크}")

        rows = await MessageTemplate.filter(kind=MessageTemplateKind.CHECK_D7)
        assert len(rows) == 1 and "둘" in rows[0].body

    async def test_reverting_deletes_the_row(self) -> None:
        """**기본 문구를 다시 베껴 넣지 않는다.** 그러면 나중에 기본 문구를
        고쳐도 되돌린 의원만 옛 글을 계속 쓴다."""
        staff = await self.a_staff(["doctor"], "revert")
        await self.save(staff, MessageTemplateKind.CHECK_D7, "{환자명}님 고침 {링크}")

        async with self.client() as client:
            response = await client.delete("/api/v1/message-templates/CHECK_D7", headers=await self.headers(staff))

        assert response.status_code == 200
        assert await MessageTemplate.all().count() == 0
        back = [row for row in response.json()["items"] if row["kind"] == "CHECK_D7"][0]
        assert back["is_default"] is True and back["body"] == DEFAULT_BODY[MessageTemplateKind.CHECK_D7]

    # ── 지울 수 없는 변수 ────────────────────────────────

    async def test_the_link_cannot_be_removed(self) -> None:
        """원문: 「{링크}는 지울 수 없다」. 링크가 빠지면 환자가 열 곳이 없다."""
        staff = await self.a_staff(["doctor"], "nolink")

        response = await self.save(staff, MessageTemplateKind.CHECK_D7, "{환자명}님, 오늘 어떠세요?")

        assert response.status_code == 422
        assert response.json()["code"] == "REQUIRED_VARIABLE_MISSING"
        assert await MessageTemplate.all().count() == 0, "막았으면 줄도 안 생겨야 한다"

    async def test_the_booking_link_cannot_be_removed_either(self) -> None:
        staff = await self.a_staff(["doctor"], "nobook")

        response = await self.save(staff, MessageTemplateKind.RUN_OUT, "[{의원명}] 약이 곧 떨어집니다")

        assert response.status_code == 422
        assert response.json()["code"] == "REQUIRED_VARIABLE_MISSING"

    async def test_a_variable_nobody_can_fill_is_refused(self) -> None:
        """채울 데가 없는 이름은 **그 글자가 그대로 환자에게 간다.**"""
        staff = await self.a_staff(["doctor"], "unknown")

        response = await self.save(staff, MessageTemplateKind.CHECK_D7, "{휴대폰}님 {링크}")

        assert response.status_code == 422
        assert response.json()["code"] == "UNKNOWN_VARIABLE"

    async def test_an_empty_body_is_refused(self) -> None:
        staff = await self.a_staff(["doctor"], "empty")

        response = await self.save(staff, MessageTemplateKind.CHECK_D7, "   ")

        assert response.status_code == 400
        assert response.json()["code"] == "EMPTY_BODY"

    # ── 권한 ─────────────────────────────────────────────

    async def test_staff_can_write_too(self) -> None:
        """**스탭도 고친다** — 2026-09-02 회의에서 설정 수정 권한을 열었다.

        원문 D2-5 는 「수정은 의사 계정만 — 문자도 환자에게 가는 안내다 ·
        스탭은 열람」이었다. 그 규칙이 바뀌었다.

        문자 문구는 **의원 단위**라 「누구 것」이 없다. 그래서 남는 규칙도
        없다 — 같은 의원이면 고친다.
        """
        clinic = await Hospital.create(name="도로시여성의원")
        staff = await self.a_staff(["staff"], "readonly", clinic)

        assert (await self.fetch(staff))["items"], "스탭도 볼 수는 있다"

        response = await self.save(staff, MessageTemplateKind.CHECK_D7, "{환자명}님 {링크}")

        assert response.status_code == 200, response.text

    async def test_another_clinic_does_not_see_the_edit(self) -> None:
        mine = await Hospital.create(name="도로시여성의원")
        theirs = await Hospital.create(name="다른의원")
        doctor = await self.a_staff(["doctor"], "scope-mine", mine)
        outsider = await self.a_staff(["doctor"], "scope-theirs", theirs)
        await self.save(doctor, MessageTemplateKind.CHECK_D7, "{환자명}님 우리 문구 {링크}")

        body = await self.fetch(outsider)

        row = [item for item in body["items"] if item["kind"] == "CHECK_D7"][0]
        assert row["is_default"] is True, "남의 의원 문구가 새면 안 된다"

    async def test_signed_out_cannot_look(self) -> None:
        async with self.client() as client:
            response = await client.get("/api/v1/message-templates")
        assert response.status_code == 401


class SmsCountingTestCase(TestCase):
    """**바이트 셈이 EUC-KR 기준이어야 하는 이유.**

    문자 단가를 정하는 것이 그 셈이다. UTF-8 로 세면 한글이 3바이트라 90바이트
    제한이 실제보다 훨씬 빨리 걸려, 보낼 수 있는 문구를 못 보낸다고 말하게 된다.
    """

    def test_korean_is_two_bytes_and_ascii_is_one(self) -> None:
        assert sms_bytes("가") == 2
        assert sms_bytes("a") == 1
        assert sms_bytes("가a") == 3
        assert sms_bytes("") == 0

    def test_utf8_would_lie(self) -> None:
        korean = "안녕하세요" * 10

        assert sms_bytes(korean) == 100
        assert len(korean.encode()) == 150, "UTF-8 로 세면 못 보낸다고 잘못 말한다"

    def test_the_defaults_land_where_the_wireframe_says(self) -> None:
        """원문이 여섯 중 **재진 안내 하나만** ⚠ 장문(LMS)으로 표시한다.

        절대 수치는 원문과 다르다 — 원문은 변수를 치환한 뒤 셌고(「92 → 85
        바이트로 줄였다」) 여기는 적힌 그대로 센다. **갈림은 같아야 한다.**
        """
        long_ones = [kind for kind, body in DEFAULT_BODY.items() if sms_bytes(body) > SMS_LIMIT]

        assert long_ones == [MessageTemplateKind.REVISIT]

    def test_variables_are_found_by_name(self) -> None:
        assert variables_in("[{의원명}] {환자명}님 {링크}") == ["의원명", "환자명", "링크"]
        assert variables_in("변수 없음") == []
        assert variables_in(None) == []
