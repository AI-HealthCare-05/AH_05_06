"""발송 이력 — KEY-234, 와이어프레임 S2-4.

원문 캡션: 「기간으로 본다 · 실패 건은 맨 위에 고정」. 설계 주석이 왜인지도
적는다 — 「실패 건은 목록에 섞이면 묻히므로 맨 위에 따로 고정한다.」

발송 예정(S2-3)과 **묻는 것이 다르다.** 저쪽은 「앞으로 무엇이 나가나」라
시각 오름차순이고, 이쪽은 「무엇이 나갔나」라 최신이 위다.

**아직 아무도 `SENT` 를 만들지 않는다.** 문자를 실제로 보내는 발송기가 없어서
`SCHEDULED` 와 `CANCELED` 만 실제로 쓰인다. 이 검사가 손으로 넣는 것은
그래서다 — 발송기가 붙는 날 화면이 이미 준비돼 있어야 한다.
"""

from datetime import date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.time import DISPLAY_TIMEZONE, clinic_today
from app.core.utils.security import hash_password
from app.main import app
from app.models.patients import Patient, PatientGender
from app.models.prescriptions import Prescription
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageFailure,
    GuideMessageKind,
    GuideMessageStatus,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
from app.services.message_history import MAX_DAYS, happened_at, sort_key
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

TODAY = clinic_today()
BIRTH = date(1992, 5, 20)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=DISPLAY_TIMEZONE).replace(hour=hour, minute=minute)


class SentHistoryTestCase(TestCase):
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
        status: GuideMessageStatus,
        sent_at: datetime | None = None,
        scheduled_at: datetime | None = None,
        kind: GuideMessageKind = GuideMessageKind.GUIDE,
        failure: GuideMessageFailure | None = None,
        viewed_at: datetime | None = None,
        prescription_set: str | None = "자궁내막증 · 비잔",
        chart: str | None = None,
    ) -> GuideMessage:
        when = scheduled_at or sent_at
        assert when is not None, "언제 일이 있었는지는 있어야 한다"
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=chart or f"{abs(hash(name)) % 90000 + 10000}",
            name=name,
            birth_date=BIRTH,
            gender=PatientGender.FEMALE,
            phone="01044524085",
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id, patient=patient, visited_at=when - timedelta(days=1)
        )
        if prescription_set is not None:
            await Prescription.create(visit=visit, prescription_set=prescription_set)
        document = await GuideDocument.create(hospital_id=hospital.hospital_id, visit=visit)
        if viewed_at is not None:
            await PatientUsageEvent.create(guide_document=document, event_type=PatientUsageEventType.GUIDE_VIEWED)
        return await GuideMessage.create(
            guide_document=document,
            kind=kind,
            status=status,
            scheduled_at=when,
            sent_at=sent_at,
            failure_code=failure,
        )

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def fetch(self, staff: Staff, path: str = "/api/v1/messages/history", **params) -> dict:
        params.setdefault("from", (TODAY - timedelta(days=7)).isoformat())
        params.setdefault("to", TODAY.isoformat())
        async with self.client() as client:
            response = await client.get(path, headers=await self.sign_in(staff), params=params)
        assert response.status_code == 200, response.text
        return response.json()

    # ── 기간 ─────────────────────────────────────────────

    async def test_only_the_chosen_period_is_listed(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "range")
        await self.a_message(
            clinic, name="사흘전", status=GuideMessageStatus.SENT, sent_at=at(TODAY - timedelta(days=3), 18)
        )
        await self.a_message(
            clinic, name="스무날전", status=GuideMessageStatus.SENT, sent_at=at(TODAY - timedelta(days=20), 18)
        )

        body = await self.fetch(staff)

        assert [item["name"] for item in body["items"]] == ["사흘전"]
        assert body["counts"]["total"] == 1

    async def test_the_period_includes_both_ends(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "ends")
        first = TODAY - timedelta(days=7)
        await self.a_message(clinic, name="첫날자정", status=GuideMessageStatus.SENT, sent_at=at(first, 0))
        await self.a_message(clinic, name="끝날밤", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 23, 59))

        body = await self.fetch(staff)

        assert len(body["items"]) == 2, "고른 날의 자정과 밤이 창 밖으로 나가면 안 된다"

    async def test_a_backwards_range_is_refused(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "backwards")
        async with self.client() as client:
            response = await client.get(
                "/api/v1/messages/history",
                headers=await self.sign_in(staff),
                params={"from": TODAY.isoformat(), "to": (TODAY - timedelta(days=1)).isoformat()},
            )
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_RANGE"

    async def test_too_long_a_range_is_refused(self) -> None:
        """조용히 줄이지 않는다 — 줄이면 화면이 「1년치를 봤다」고 믿는다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "toolong")
        async with self.client() as client:
            response = await client.get(
                "/api/v1/messages/history",
                headers=await self.sign_in(staff),
                params={"from": (TODAY - timedelta(days=MAX_DAYS)).isoformat(), "to": TODAY.isoformat()},
            )
        assert response.status_code == 400
        assert response.json()["code"] == "RANGE_TOO_LONG"

    # ── 담기는 것 ────────────────────────────────────────

    async def test_only_what_already_happened(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "happened")
        await self.a_message(clinic, name="나감", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 10))
        await self.a_message(clinic, name="예정", status=GuideMessageStatus.SCHEDULED, scheduled_at=at(TODAY, 11))
        await self.a_message(clinic, name="보류", status=GuideMessageStatus.HELD, scheduled_at=at(TODAY, 12))
        await self.a_message(clinic, name="꺼짐", status=GuideMessageStatus.CANCELED, scheduled_at=at(TODAY, 13))

        body = await self.fetch(staff)

        assert [item["name"] for item in body["items"]] == ["나감"], "앞일은 S2-3 이 본다"

    async def test_a_failed_row_falls_back_to_the_planned_time(self) -> None:
        """못 나간 줄에는 `sent_at` 이 없는데 원문은 실패 줄에도 시각을 적는다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "fallback")
        planned = at(TODAY, 10, 6)
        await self.a_message(
            clinic,
            name="박수빈",
            status=GuideMessageStatus.FAILED,
            scheduled_at=planned,
            failure=GuideMessageFailure.INVALID_PHONE,
        )

        item = (await self.fetch(staff))["items"][0]

        assert item["happened_at"].startswith(planned.isoformat()[:16])
        assert item["failure_code"] == "INVALID_PHONE"

    def test_happened_at_prefers_the_time_it_actually_went(self) -> None:
        planned, went = at(TODAY, 10), at(TODAY, 11)
        assert happened_at(GuideMessage(scheduled_at=planned, sent_at=went)) == went
        assert happened_at(GuideMessage(scheduled_at=planned, sent_at=None)) == planned

    # ── 줄 순서 ──────────────────────────────────────────

    async def test_failed_rows_are_pinned_on_top(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "pin")
        await self.a_message(clinic, name="최근완료", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 18))
        await self.a_message(
            clinic,
            name="옛실패",
            status=GuideMessageStatus.FAILED,
            scheduled_at=at(TODAY - timedelta(days=5), 10),
            failure=GuideMessageFailure.CARRIER,
        )

        body = await self.fetch(staff)

        assert [item["name"] for item in body["items"]] == ["옛실패", "최근완료"], (
            "원문: 「실패 건은 목록에 섞이면 묻히므로 맨 위에 따로 고정한다」"
        )

    def test_history_reads_newest_first(self) -> None:
        """발송 예정(S2-3)과 반대다 — 이력은 방금 무슨 일이 있었나를 먼저 묻는다."""
        older = sort_key(GuideMessageStatus.SENT, at(TODAY - timedelta(days=1), 10))
        newer = sort_key(GuideMessageStatus.SENT, at(TODAY, 10))
        assert newer < older
        assert sort_key(GuideMessageStatus.FAILED, at(TODAY - timedelta(days=9), 1)) < newer

    # ── 열람 ─────────────────────────────────────────────

    async def test_viewing_is_per_guide_not_per_message(self) -> None:
        """링크 하나가 안내문 하나를 연다 — 어느 문자를 보고 열었는지는 물을 수 없다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "viewed")
        message = await self.a_message(
            clinic,
            name="서다은",
            status=GuideMessageStatus.SENT,
            sent_at=at(TODAY, 16, 12),
            viewed_at=at(TODAY, 17),
        )
        # 같은 안내문에 달린 둘째 통
        await GuideMessage.create(
            guide_document_id=message.guide_document_id,
            kind=GuideMessageKind.CHECK_D7,
            status=GuideMessageStatus.SENT,
            scheduled_at=at(TODAY, 9),
            sent_at=at(TODAY, 9),
        )

        body = await self.fetch(staff)

        assert len(body["items"]) == 2
        assert all(item["viewed"] for item in body["items"]), "한 번 열면 그 안내문의 문자가 다 열람이다"
        assert body["counts"]["viewed"] == 2

    async def test_counts_add_up_the_way_the_wireframe_says(self) -> None:
        """원문: 전체 210 · 실패 1 · 미열람 34 · 열람 175 — 175 + 34 = 210 − 1."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "counts")
        await self.a_message(
            clinic, name="열람", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 10), viewed_at=at(TODAY, 11)
        )
        await self.a_message(clinic, name="미열람", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 12))
        await self.a_message(
            clinic,
            name="실패",
            status=GuideMessageStatus.FAILED,
            scheduled_at=at(TODAY, 13),
            failure=GuideMessageFailure.OPT_OUT,
        )

        counts = (await self.fetch(staff))["counts"]

        assert counts == {"total": 3, "failed": 1, "viewed": 1, "unviewed": 1}
        assert counts["viewed"] + counts["unviewed"] == counts["total"] - counts["failed"], (
            "못 나간 문자에 열람을 묻는 것은 뜻이 없다"
        )

    async def test_a_failed_row_does_not_count_as_viewed(self) -> None:
        """**같은 안내문의 앞 통이 나가고 열렸는데 뒤 통이 실패했다.**

        열람은 안내문 단위라 그 문서에는 열람 기록이 있다. 그래도 실패 줄을
        열람으로 세면 안 된다 — 원문의 수가 그렇게 맞는다(175 + 34 = 210 − 1).
        이 자리를 안 만들어 두면 「나간 것 중에서만 센다」를 지워 놓아도
        검사가 통과한다.
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "failed-viewed")
        sent = await self.a_message(
            clinic, name="박수빈", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 9), viewed_at=at(TODAY, 10)
        )
        await GuideMessage.create(
            guide_document_id=sent.guide_document_id,
            kind=GuideMessageKind.CHECK_D7,
            status=GuideMessageStatus.FAILED,
            scheduled_at=at(TODAY, 11),
            failure_code=GuideMessageFailure.CARRIER,
        )

        counts = (await self.fetch(staff))["counts"]

        assert counts == {"total": 2, "failed": 1, "viewed": 1, "unviewed": 0}
        assert counts["viewed"] + counts["unviewed"] == counts["total"] - counts["failed"]

    # ── 격리 · 권한 ──────────────────────────────────────

    async def test_another_clinic_is_invisible(self) -> None:
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        staff = await self.a_staff(mine, ["staff"], "hist-scope")
        await self.a_message(mine, name="우리환자", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 10))
        await self.a_message(theirs, name="남의환자", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 10))

        body = await self.fetch(staff)

        assert [item["name"] for item in body["items"]] == ["우리환자"]

    async def test_the_hospital_copy_is_not_trusted(self) -> None:
        """격리는 `visit` 을 타고 판단한다 — `guide_document.hospital_id` 는 사본이다."""
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        staff = await self.a_staff(mine, ["staff"], "hist-copy")
        message = await self.a_message(theirs, name="남의환자", status=GuideMessageStatus.SENT, sent_at=at(TODAY, 10))
        document = await GuideDocument.get(guide_document_id=message.guide_document_id)
        document.hospital_id = mine.hospital_id
        await document.save(update_fields=["hospital_id"])

        body = await self.fetch(staff)

        assert body["items"] == [], "사본을 믿으면 남의 의원 환자가 열린다"

    async def test_admin_only_cannot_look(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["admin"], "hist-admin")
        async with self.client() as client:
            response = await client.get(
                "/api/v1/messages/history",
                headers=await self.sign_in(staff),
                params={"from": TODAY.isoformat(), "to": TODAY.isoformat()},
            )
        assert response.status_code == 403

    # ── 잘림 ─────────────────────────────────────────────

    async def test_failed_rows_are_never_truncated(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "hist-trunc")
        for hour in (9, 10, 11):
            await self.a_message(
                clinic,
                name=f"실패{hour}",
                status=GuideMessageStatus.FAILED,
                scheduled_at=at(TODAY, hour),
                failure=GuideMessageFailure.CARRIER,
            )
        for hour in (13, 14, 15):
            await self.a_message(clinic, name=f"완료{hour}", status=GuideMessageStatus.SENT, sent_at=at(TODAY, hour))

        body = await self.fetch(staff, limit=1)

        names = [item["name"] for item in body["items"]]
        assert names[:3] == ["실패11", "실패10", "실패9"], "맨 위에 고정하라 해 놓고 잘라 내면 까닭이 없어진다"
        assert len([n for n in names if n.startswith("완료")]) == 1
        assert body["truncated"] is True
        assert body["counts"]["total"] == 6, "잘라도 몇 건인지는 말한다"
