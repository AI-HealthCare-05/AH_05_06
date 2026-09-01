"""발송 예정 — KEY-234, 와이어프레임 S2-3.

**두 규칙이 이 화면의 전부다.**

1. 안 나간 것(실패 · 보류)은 고른 기간 밖이어도 보인다 — 원문에서 박수빈의
   08-11 실패는 지난 것이고 강예린의 11-06 보류는 「앞으로 7일」 밖인데 둘 다
   떠 있다. 놓치면 환자가 문자를 못 받는다.
2. 예정은 고른 기간 안의 것만.

**아직 아무도 `HELD` · `FAILED` 를 만들지 않는다.** 발송기 자체가 없어서
`SCHEDULED` 와 `CANCELED` 만 실제로 쓰인다. 이 검사가 두 상태를 손으로 만들어
넣는 것은 그래서다 — 발송기가 붙는 날 화면이 이미 준비돼 있어야 한다.
"""

from datetime import date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.time import DISPLAY_TIMEZONE, clinic_today
from app.core.utils.security import hash_password
from app.dtos.patients import calculate_age
from app.main import app
from app.models.patients import Patient, PatientGender
from app.models.prescriptions import Prescription
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageFailure,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    Visit,
)
from app.services.message_schedule import sort_key
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

#: **라우터가 진짜 오늘을 쓴다.** 그래서 검사도 오늘에서 재고, 날짜는 전부
#: 상대로 적는다 — 고정 날짜를 박으면 그 날이 지나는 순간 창 밖으로 나간다.
TODAY = clinic_today()
BIRTH = date(1992, 5, 20)


def at(day: date, hour: int) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=DISPLAY_TIMEZONE).replace(hour=hour)


class ScheduledMessagesTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_clinic(self, name: str = "도로시여성의원") -> Hospital:
        return await Hospital.create(name=name)

    async def a_staff(self, hospital: Hospital, roles: list[str], login: str) -> Staff:
        return await Staff.create(
            hospital=hospital,
            login_id=login,
            password_hash=hash_password("pw"),
            name="서지현",
            roles=roles,
            must_change_password=False,
        )

    async def sign_in(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    async def a_message(
        self,
        hospital: Hospital,
        *,
        name: str,
        when: datetime,
        status: GuideMessageStatus,
        kind: GuideMessageKind = GuideMessageKind.GUIDE,
        hold: GuideMessageHold | None = None,
        failure: GuideMessageFailure | None = None,
        prescription_set: str | None = "자궁내막증 · 초진",
        chart: str | None = None,
    ) -> GuideMessage:
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=chart or f"{abs(hash(name + when.isoformat())) % 90000 + 10000}",
            name=name,
            birth_date=BIRTH,
            gender=PatientGender.FEMALE,
            phone="01044524085",
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            visited_at=when - timedelta(days=1),
        )
        if prescription_set is not None:
            await Prescription.create(visit=visit, prescription_set=prescription_set)
        document = await GuideDocument.create(hospital_id=hospital.hospital_id, visit=visit)
        return await GuideMessage.create(
            guide_document=document,
            kind=kind,
            status=status,
            scheduled_at=when,
            hold_reason=hold,
            failure_code=failure,
        )

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def fetch(self, staff: Staff, **params) -> dict:
        async with self.client() as client:
            response = await client.get(
                "/api/v1/messages/scheduled",
                headers=await self.sign_in(staff),
                params=params,
            )
        assert response.status_code == 200, response.text
        return response.json()

    # ── 규칙 1 · 안 나간 것은 창 밖이어도 보인다 ──────────────

    async def test_unsent_shows_outside_the_window(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "unsent")
        await self.a_message(
            clinic,
            name="박수빈",
            when=at(TODAY - timedelta(days=3), 18),
            status=GuideMessageStatus.FAILED,
            failure=GuideMessageFailure.INVALID_PHONE,
        )
        await self.a_message(
            clinic,
            name="강예린",
            when=at(TODAY + timedelta(days=84), 10),
            status=GuideMessageStatus.HELD,
            hold=GuideMessageHold.NO_CREDIT,
        )

        body = await self.fetch(staff, days=7)

        names = [item["name"] for item in body["items"]]
        assert names == ["박수빈", "강예린"], "지난 실패와 먼 보류가 둘 다 떠야 한다"
        assert body["counts"]["failed"] == 1
        assert body["counts"]["held"] == 1
        assert body["counts"]["window"] == 0, "예정이 아니므로 기간 셈에는 안 든다"

    async def test_canceled_and_sent_are_gone(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "canceled")
        await self.a_message(
            clinic,
            name="김서연",
            when=at(TODAY, 18),
            status=GuideMessageStatus.CANCELED,
        )
        await self.a_message(
            clinic,
            name="이서아",
            when=at(TODAY, 18),
            status=GuideMessageStatus.SENT,
        )

        body = await self.fetch(staff, days=7)

        assert body["items"] == [], "껐거나 이미 나간 것은 앞으로 나갈 것이 아니다"
        assert body["counts"]["total"] == 0

    # ── 규칙 2 · 예정은 창 안의 것만 ────────────────────────

    async def test_scheduled_obeys_the_window(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "window")
        await self.a_message(clinic, name="오늘", when=at(TODAY, 18), status=GuideMessageStatus.SCHEDULED)
        await self.a_message(
            clinic, name="나흘뒤", when=at(TODAY + timedelta(days=4), 10), status=GuideMessageStatus.SCHEDULED
        )
        await self.a_message(
            clinic, name="스무날뒤", when=at(TODAY + timedelta(days=20), 10), status=GuideMessageStatus.SCHEDULED
        )

        seven = await self.fetch(staff, days=7)
        thirty = await self.fetch(staff, days=30)

        assert [item["name"] for item in seven["items"]] == ["오늘", "나흘뒤"]
        assert seven["counts"]["window"] == 2
        assert seven["counts"]["today"] == 1
        assert seven["counts"]["total"] == 3, "전체는 창과 무관하게 센다 — 원문의 「전체 42」"
        assert [item["name"] for item in thirty["items"]] == ["오늘", "나흘뒤", "스무날뒤"]

    async def test_the_window_starts_at_midnight_today(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "past")
        await self.a_message(
            clinic, name="어제", when=at(TODAY - timedelta(days=1), 10), status=GuideMessageStatus.SCHEDULED
        )

        body = await self.fetch(staff, days=7)

        assert body["items"] == [], "창은 오늘 0시부터다"
        assert body["counts"]["total"] == 1, "그래도 어딘가에 남아 있다는 것은 센다"

    # ── 줄 순서 ───────────────────────────────────────────

    async def test_unsent_rows_come_first(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "order")
        await self.a_message(clinic, name="예정", when=at(TODAY, 9), status=GuideMessageStatus.SCHEDULED)
        await self.a_message(
            clinic,
            name="보류",
            when=at(TODAY + timedelta(days=3), 10),
            status=GuideMessageStatus.HELD,
            hold=GuideMessageHold.INVALID_PHONE,
        )
        await self.a_message(
            clinic,
            name="실패",
            when=at(TODAY - timedelta(days=3), 18),
            status=GuideMessageStatus.FAILED,
            failure=GuideMessageFailure.INVALID_PHONE,
        )

        body = await self.fetch(staff, days=7)

        assert [item["name"] for item in body["items"]] == ["실패", "보류", "예정"], (
            "예정이 더 이른 시각인데도 안 나간 것이 위여야 한다"
        )

    def test_order_does_not_split_failed_from_held(self) -> None:
        early_hold = sort_key(GuideMessageStatus.HELD, at(TODAY, 9))
        late_fail = sort_key(GuideMessageStatus.FAILED, at(TODAY, 18))
        assert early_hold < late_fail, "안 나간 것 안에서는 시각만 본다"
        assert sort_key(GuideMessageStatus.SCHEDULED, at(TODAY, 1)) > late_fail

    # ── 의원 격리 ─────────────────────────────────────────

    async def test_another_clinic_is_invisible(self) -> None:
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        staff = await self.a_staff(mine, ["staff"], "scope-mine")
        await self.a_message(mine, name="우리환자", when=at(TODAY, 18), status=GuideMessageStatus.SCHEDULED)
        await self.a_message(theirs, name="남의환자", when=at(TODAY, 18), status=GuideMessageStatus.SCHEDULED)

        body = await self.fetch(staff, days=7)

        assert [item["name"] for item in body["items"]] == ["우리환자"]
        assert body["counts"]["total"] == 1

    async def test_the_hospital_copy_is_not_trusted(self) -> None:
        """**격리는 `visit` 을 타고 판단한다** — `guide_document.hospital_id` 는
        목록을 거르는 인덱스용 사본이다.

        사본과 진짜가 어긋난 줄을 손으로 만든다. 둘이 늘 같은 자료만 넣고
        재면, 사본으로 판단하도록 고쳐 놓아도 검사가 통과한다 — 실제로
        그렇게 두었더니 돌연변이가 안 물었다.
        """
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        staff = await self.a_staff(mine, ["staff"], "scope-copy")

        message = await self.a_message(theirs, name="남의환자", when=at(TODAY, 18), status=GuideMessageStatus.SCHEDULED)
        document = await GuideDocument.get(guide_document_id=message.guide_document_id)
        document.hospital_id = mine.hospital_id
        await document.save(update_fields=["hospital_id"])

        body = await self.fetch(staff, days=7)

        assert body["items"] == [], "사본을 믿으면 남의 의원 환자가 열린다"

    # ── 권한 ─────────────────────────────────────────────

    async def test_both_staff_and_doctor_can_look(self) -> None:
        clinic = await self.a_clinic()
        await self.a_message(clinic, name="김서연", when=at(TODAY, 18), status=GuideMessageStatus.SCHEDULED)

        for roles, login in ((["staff"], "sees-staff"), (["doctor"], "sees-doctor")):
            staff = await self.a_staff(clinic, roles, login)
            body = await self.fetch(staff, days=7)
            assert len(body["items"]) == 1, f"{roles} 가 못 본다"

    async def test_admin_only_cannot_look(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["admin"], "admin-only")
        async with self.client() as client:
            response = await client.get(
                "/api/v1/messages/scheduled", headers=await self.sign_in(staff), params={"days": 7}
            )
        assert response.status_code == 403

    async def test_signed_out_cannot_look(self) -> None:
        async with self.client() as client:
            response = await client.get("/api/v1/messages/scheduled", params={"days": 7})
        assert response.status_code == 401

    # ── 줄에 담기는 것 ─────────────────────────────────────

    async def test_a_row_carries_what_the_screen_shows(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "row")
        await self.a_message(
            clinic,
            name="박수빈",
            when=at(TODAY - timedelta(days=3), 18),
            status=GuideMessageStatus.FAILED,
            failure=GuideMessageFailure.INVALID_PHONE,
            prescription_set="자궁내막증 · 초진",
            chart="09871",
        )

        item = (await self.fetch(staff, days=7))["items"][0]

        assert item["name"] == "박수빈"
        assert item["hospital_patient_no"] == "09871"
        assert item["gender"] == "FEMALE"
        assert item["birth_date"] == BIRTH.isoformat()
        assert item["age"] == calculate_age(BIRTH, as_of=TODAY)
        assert item["prescription_set"] == "자궁내막증 · 초진"
        assert item["kind"] == "GUIDE"
        assert item["status"] == "FAILED"
        assert item["failure_code"] == "INVALID_PHONE"
        assert item["hold_reason"] is None
        assert item["visit_id"] and item["patient_id"], "번호를 고치러 갈 곳이 있어야 한다"

    async def test_no_prescription_means_no_set_name(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "noset")
        await self.a_message(
            clinic, name="장소윤", when=at(TODAY, 18), status=GuideMessageStatus.SCHEDULED, prescription_set=None
        )

        item = (await self.fetch(staff, days=7))["items"][0]

        assert item["prescription_set"] is None, "없는 것을 지어내지 않는다"

    # ── 잘림 ─────────────────────────────────────────────

    async def test_a_truncated_page_says_so(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "trunc")
        for hour in (9, 10, 11):
            await self.a_message(clinic, name=f"예정{hour}", when=at(TODAY, hour), status=GuideMessageStatus.SCHEDULED)

        body = await self.fetch(staff, days=7, limit=2)

        assert len(body["items"]) == 2
        assert body["truncated"] is True
        assert body["counts"]["window"] == 3, "잘라도 몇 건인지는 말한다"

    async def test_unsent_is_never_truncated(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "trunc-unsent")
        for hour in (9, 10, 11):
            await self.a_message(
                clinic,
                name=f"보류{hour}",
                when=at(TODAY, hour),
                status=GuideMessageStatus.HELD,
                hold=GuideMessageHold.INVALID_PHONE,
            )

        body = await self.fetch(staff, days=7, limit=1)

        assert len(body["items"]) == 3, "이 화면의 요점을 잘라 내면 안 된다"
        assert body["truncated"] is False

    # ── 입력 ─────────────────────────────────────────────

    async def test_days_must_be_in_range(self) -> None:
        """`ContractRoute` 가 검증 오류를 `400 INVALID_REQUEST` 로 옮긴다 —
        FastAPI 기본값 422 가 아니다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "days")
        headers = await self.sign_in(staff)
        async with self.client() as client:
            for days in (0, 91, -1):
                response = await client.get("/api/v1/messages/scheduled", headers=headers, params={"days": days})
                assert response.status_code == 400, f"days={days} 가 통과했다"
                assert response.json()["code"] == "INVALID_REQUEST"
