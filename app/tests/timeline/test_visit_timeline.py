"""진료 처리 이력 — KEY-234, 와이어프레임 D1-6.

승인 뒤에 무슨 일이 있었는지 볼 자리가 없었다 — 보냈는지 · 열었는지 ·
답했는지가 어디에도 안 보였다.

**시스템이 한 일도 숨기지 않는다.** 사람이 한 것만 보면 절반이 빈다.
"""

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    CheckIn,
    CheckInMedication,
    GuideDocument,
    GuideEvent,
    GuideEventType,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

BASE = "/api/v1/visits"


class TimelineTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def make_staff(self, hospital: Hospital, login_id: str, roles: list[str], name: str) -> Staff:
        return await Staff.create(
            hospital=hospital,
            login_id=login_id,
            password_hash=hash_password("Password123!"),
            name=name,
            roles=roles,
            must_change_password=False,
        )

    async def make_visit(self, hospital: Hospital, chart: str = "TL-01") -> Visit:
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=chart,
            name="김서연",
            birth_date="1990-01-01",
            phone="01000000000",
        )
        return await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 8, 13, 10, 32, tzinfo=UTC),
        )

    async def sign_in(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_visit_alone_still_has_a_beginning(self) -> None:
        """안내문이 없어도 **등록은 있었다.** 빈 목록을 주면 화면이
        「고장」으로 읽고, 진료가 언제 시작됐는지를 못 보여 준다."""
        clinic = await Hospital.create(name="여성의원")
        staff = await self.make_staff(clinic, "tl_staff", ["staff"], "서지현")
        visit = await self.make_visit(clinic)

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline", headers=await self.sign_in(staff))

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["visit_id"] == visit.visit_id
        assert [e["kind"] for e in body["entries"]] == ["VISIT_CREATED"]

    async def test_three_tables_merge_in_time_order(self) -> None:
        """사람이 한 일 · 환자가 한 일 · 확인 응답이 **한 줄기로** 선다.

        오래된 것이 위다 — 진료가 어떻게 흘러갔는지 읽는 자리라, 최신순으로
        뒤집으면 거꾸로 읽게 된다.
        """
        clinic = await Hospital.create(name="여성의원")
        staff = await self.make_staff(clinic, "tl_staff2", ["staff"], "서지현")
        visit = await self.make_visit(clinic, "TL-02")
        guide = await GuideDocument.create(hospital_id=clinic.hospital_id, visit=visit)

        # 일부러 **거꾸로** 넣는다 — 넣은 차례가 아니라 시각으로 서야 한다
        await PatientUsageEvent.create(
            guide_document=guide,
            event_type=PatientUsageEventType.GUIDE_VIEWED,
            created_at=datetime(2026, 8, 13, 19, 14, tzinfo=UTC),
        )
        await CheckIn.create(
            guide_document=guide,
            medication=CheckInMedication.TAKING,
            pain_types=[],
            created_at=datetime(2026, 8, 20, 10, 5, tzinfo=UTC),
        )
        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.APPROVED,
            actor_id=staff.staff_id,
            created_at=datetime(2026, 8, 13, 11, 2, tzinfo=UTC),
        )

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline", headers=await self.sign_in(staff))

        assert res.status_code == 200, res.text
        kinds = [e["kind"] for e in res.json()["entries"]]
        assert kinds == ["VISIT_CREATED", "APPROVED", "GUIDE_VIEWED", "CHECK_IN"], kinds

    async def test_person_gets_a_name_and_system_does_not(self) -> None:
        """사람이 한 것은 이름이 뜨고, 환자가 한 것은 비어 있다.

        빈 문자열로 두면 **이름이 없는 사람**과 섞인다 — 화면이 「시스템」과
        「알 수 없음」을 가를 수 없다.
        """
        clinic = await Hospital.create(name="여성의원")
        staff = await self.make_staff(clinic, "tl_doc", ["doctor"], "박연")
        visit = await self.make_visit(clinic, "TL-03")
        guide = await GuideDocument.create(hospital_id=clinic.hospital_id, visit=visit)

        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.APPROVED,
            actor_id=staff.staff_id,
            created_at=datetime(2026, 8, 13, 11, 2, tzinfo=UTC),
        )
        await PatientUsageEvent.create(
            guide_document=guide,
            event_type=PatientUsageEventType.GUIDE_VIEWED,
            created_at=datetime(2026, 8, 13, 19, 14, tzinfo=UTC),
        )

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline", headers=await self.sign_in(staff))

        by_kind = {e["kind"]: e for e in res.json()["entries"]}
        assert by_kind["APPROVED"]["actor"] == "박연"
        assert by_kind["GUIDE_VIEWED"]["actor"] is None, "환자가 한 것에 이름이 붙었다"

    async def test_deleted_actor_gets_no_invented_name(self) -> None:
        """**지워진 계정에 이름을 지어내지 않는다.**

        「알 수 없음」을 서버가 적어 버리면 화면은 그것이 사람 이름인지
        시스템인지 가를 수 없다 — 환자가 한 일과 같은 모양이 된다.
        비워서 보내고, 무엇이라 적을지는 화면이 정한다.
        """
        clinic = await Hospital.create(name="여성의원")
        staff = await self.make_staff(clinic, "tl_gone", ["staff"], "서지현")
        visit = await self.make_visit(clinic, "TL-07")
        guide = await GuideDocument.create(hospital_id=clinic.hospital_id, visit=visit)

        # 이 저장소에 없는 직원 번호로 남긴 기록
        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.EDITED,
            actor_id=999_999,
            created_at=datetime(2026, 8, 13, 10, 43, tzinfo=UTC),
        )

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline", headers=await self.sign_in(staff))

        row = [e for e in res.json()["entries"] if e["kind"] == "EDITED"][0]
        assert row["actor"] is None, f"없는 계정에 이름을 지어냈다: {row['actor']!r}"

    async def test_returned_reason_rides_along(self) -> None:
        """되돌린 사유가 그 줄에 붙는다 — 무엇을 고쳐야 하는지가 흐름에서
        보여야, 스탭이 알림을 다시 찾아가지 않는다."""
        clinic = await Hospital.create(name="여성의원")
        doctor = await self.make_staff(clinic, "tl_doc2", ["doctor"], "박연")
        visit = await self.make_visit(clinic, "TL-04")
        guide = await GuideDocument.create(hospital_id=clinic.hospital_id, visit=visit)

        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.RETURNED,
            actor_id=doctor.staff_id,
            reason="진료기록 재업로드 필요",
            created_at=datetime(2026, 8, 13, 11, 10, tzinfo=UTC),
        )

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline", headers=await self.sign_in(doctor))

        row = [e for e in res.json()["entries"] if e["kind"] == "RETURNED"][0]
        assert row["detail"] == "진료기록 재업로드 필요"

    async def test_another_hospitals_visit_is_not_found(self) -> None:
        """남의 의원 것은 **없는 것이다** — 존재 여부가 새면 그 자체가 정보다."""
        mine = await Hospital.create(name="여성의원")
        theirs = await Hospital.create(name="다른의원")
        staff = await self.make_staff(theirs, "tl_other", ["staff"], "남")
        visit = await self.make_visit(mine, "TL-05")

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline", headers=await self.sign_in(staff))

        assert res.status_code == 404, f"남의 의원 진료가 {res.status_code} 로 보였다"

    async def test_requires_login(self) -> None:
        clinic = await Hospital.create(name="여성의원")
        visit = await self.make_visit(clinic, "TL-06")

        async with self.client() as client:
            res = await client.get(f"{BASE}/{visit.visit_id}/timeline")

        assert res.status_code in (401, 403)
