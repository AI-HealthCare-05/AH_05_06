"""승인 안내 링크에서 D+7 응답 한 건이 안전하게 환류하는가 — KEY-151."""

import hashlib

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.redis_client import get_redis
from app.main import app
from app.models.staffs import Hospital
from app.models.visits import (
    CheckIn,
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientGuideLink,
)
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis
from app.tests.patient_links.test_patient_links import make_guide, make_hospital, make_staff

TOKEN = "key151-synthetic-token-never-log-or-store"


async def make_linked_guide(hospital: Hospital) -> GuideDocument:
    guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.CAUTION,
        generated_body="합성 승인 주의 안내",
    )
    await PatientGuideLink.create(
        guide_document=guide,
        token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
        expires_at=now().replace(year=now().year + 1),
        issued_by=1,
    )
    return guide


class CheckInTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def headers(self, staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff, False)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}


class TestPatientCheckIn(CheckInTestCase):
    async def test_approved_sections_are_reused_and_one_response_is_linked_to_the_visit(self) -> None:
        hospital = await make_hospital("KEY-151 합성의원")
        guide = await make_linked_guide(hospital)

        async with self.client() as client:
            form = await client.get(f"/api/v1/checkins/{TOKEN}")
            saved = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={
                    "medication": "taking",
                    "pain": {"had": True, "score": 4, "types": ["menstrual"]},
                },
            )

        assert form.status_code == 200
        form_body = form.json()
        assert form_body["demo_only"] is True
        assert form_body["answered"] is False
        assert form_body["answers"]["missing"]["lead"] == "합성 승인 복약 안내"
        assert form_body["answers"]["uncomfortable"]["lead"] == "합성 승인 주의 안내"
        for forbidden in ("합성 생성 원문", TOKEN, "approved_by", "patient", "ocr"):
            assert forbidden not in form.text.lower()

        assert saved.status_code == 201
        assert saved.json()["pain"] == {"had": True, "score": 4, "types": ["menstrual"]}
        check_in = await CheckIn.get()
        assert check_in.guide_document_id == guide.guide_document_id
        assert guide.visit_id == (await check_in.guide_document).visit_id
        assert TOKEN not in repr(check_in.__dict__)

    async def test_a_second_submission_is_rejected_and_get_marks_the_round_answered(self) -> None:
        hospital = await make_hospital("KEY-151 중복 합성의원")
        await make_linked_guide(hospital)
        payload = {"medication": "missing", "pain": {"had": False, "score": None, "types": []}}

        async with self.client() as client:
            first = await client.post(f"/api/v1/checkins/{TOKEN}", json=payload)
            second = await client.post(f"/api/v1/checkins/{TOKEN}", json=payload)
            form = await client.get(f"/api/v1/checkins/{TOKEN}")

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["code"] == "CHECKIN_ALREADY_ANSWERED"
        assert form.json()["answered"] is True
        assert await CheckIn.all().count() == 1

    async def test_unapproved_guide_is_hidden_and_invalid_pain_is_rejected(self) -> None:
        hospital = await make_hospital("KEY-151 차단 합성의원")
        guide = await make_linked_guide(hospital)
        await GuideDocument.filter(guide_document_id=guide.guide_document_id).update(
            status=GuideStatus.APPROVAL_PENDING,
            approved_at=None,
        )

        async with self.client() as client:
            hidden = await client.get(f"/api/v1/checkins/{TOKEN}")
            invalid = await client.post(
                "/api/v1/checkins/not-a-real-token",
                json={"medication": "taking", "pain": {"had": False, "score": 3, "types": []}},
            )

        assert hidden.status_code == 404
        assert hidden.json()["code"] == "LINK_NOT_FOUND"
        assert invalid.status_code == 422


class TestHospitalCheckIn(CheckInTestCase):
    async def test_same_hospital_staff_reads_the_response_by_visit_id(self) -> None:
        hospital = await make_hospital("KEY-151 병원조회 합성의원")
        guide = await make_linked_guide(hospital)
        staff = await make_staff(hospital, "key151-staff", ["staff"])
        async with self.client() as client:
            assert (
                await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking", "pain": None})
            ).status_code == 201
            response = await client.get(f"/api/v1/visits/{guide.visit_id}/checkin", headers=await self.headers(staff))

        assert response.status_code == 200
        assert response.json()["visit_id"] == guide.visit_id
        assert response.json()["medication"] == "taking"
        assert response.json()["pain"] is None
        assert TOKEN not in response.text

    async def test_other_hospital_and_admin_only_access_are_blocked(self) -> None:
        owner = await make_hospital("KEY-151 소유 합성의원")
        outsider = await make_hospital("KEY-151 외부 합성의원")
        guide = await make_linked_guide(owner)
        outside_staff = await make_staff(outsider, "key151-outsider", ["staff"])
        owner_admin = await make_staff(owner, "key151-admin", ["admin"])
        async with self.client() as client:
            assert (
                await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking", "pain": None})
            ).status_code == 201
            hidden = await client.get(
                f"/api/v1/visits/{guide.visit_id}/checkin", headers=await self.headers(outside_staff)
            )
            forbidden = await client.get(
                f"/api/v1/visits/{guide.visit_id}/checkin", headers=await self.headers(owner_admin)
            )

        assert hidden.status_code == 404
        assert hidden.json()["code"] == "CHECKIN_NOT_FOUND"
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "FORBIDDEN"
