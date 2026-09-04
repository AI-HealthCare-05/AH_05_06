"""개발용 링크가 승인 안내만 안전하게 여는가 — KEY-90."""

import hashlib
from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.dependencies.patient_auth import require_patient_session
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientGuideLink,
    Visit,
)
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

TOKEN = "kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x"


async def make_hospital(name: str) -> Hospital:
    return await Hospital.create(name=name)


async def make_staff(hospital: Hospital, login_id: str, roles: list[str]) -> Staff:
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password("Synthetic-password-1!"),
        name="합성직원",
        roles=roles,
        must_change_password=False,
    )


async def make_guide(hospital: Hospital, status: GuideStatus) -> GuideDocument:
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="SYN-KEY90-01",
        name="합성환자",
        birth_date="1991-02-03",
        phone="01000007788",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at="2026-08-24T09:00:00+09:00",
    )
    approved = status is GuideStatus.SCHEDULED_TO_SEND
    guide = await GuideDocument.create(
        hospital_id=hospital.hospital_id,
        visit=visit,
        status=status,
        approved_by=1 if approved else None,
        approved_at=now() if approved else None,
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.MEDICATION,
        generated_body="합성 생성 원문 — 환자에게는 수정본이 보여야 합니다.",
        edited_body="합성 승인 복약 안내",
        warn="내부 검수용 경고 — 환자 응답에 없어야 합니다.",
    )
    return guide


class PatientLinkTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis
        app.dependency_overrides[require_patient_session] = lambda: None

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def headers(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def issue(self, guide: GuideDocument, staff: Staff):
        with patch("app.services.patient_links.secrets.token_urlsafe", return_value=TOKEN):
            async with self.client() as client:
                return await client.post(
                    f"/api/v1/visits/{guide.visit_id}/guide/link",
                    headers=await self.headers(staff),
                )


class TestIssueAndRead(PatientLinkTestCase):
    async def test_approved_guide_is_opened_for_72_hours_without_storing_raw_token(self) -> None:
        hospital = await make_hospital("KEY-90 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key90-staff", ["staff"])

        before = now()
        issued = await self.issue(guide, staff)

        assert issued.status_code == 201
        payload = issued.json()
        assert payload["demo_only"] is True
        assert payload["path"] == f"/api/v1/guides/{TOKEN}"
        expires_at = payload["expires_at"]

        saved = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert saved.token_digest == hashlib.sha256(TOKEN.encode()).hexdigest()
        assert TOKEN not in repr(saved.__dict__)
        assert before + timedelta(hours=72) <= saved.expires_at <= now() + timedelta(hours=72)

        async with self.client() as client:
            read = await client.get(payload["path"])
        assert read.status_code == 200
        body = read.json()
        assert body["demo_only"] is True
        assert body["expires_at"] == expires_at
        assert body["sections"] == [{"key": "medication", "body": "합성 승인 복약 안내"}]
        serialized = read.text
        # 인증 전(세션 쿠키 없음) 응답이라 이름도 없어야 한다. 이름은 KEY-268 에서
        # OTP 인증한 뷰어에게만 실리므로 여기서는 환자 원본 식별자 전반을 막는다.
        for forbidden in (
            "합성 생성 원문",
            "내부 검수용 경고",
            "phone",
            "patient_name",
            "hospital_patient_no",
            "birth_date",
            "합성환자",
            "approved_by",
        ):
            assert forbidden not in serialized

    async def test_the_same_guide_does_not_silently_create_multiple_links(self) -> None:
        hospital = await make_hospital("KEY-90 중복 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key90-duplicate", ["doctor"])

        first = await self.issue(guide, staff)
        second = await self.issue(guide, staff)

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["code"] == "LINK_ALREADY_ISSUED"
        assert await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).count() == 1


class TestLinkBoundaries(PatientLinkTestCase):
    async def test_unapproved_guide_is_rejected(self) -> None:
        hospital = await make_hospital("KEY-90 미승인 합성의원")
        guide = await make_guide(hospital, GuideStatus.APPROVAL_PENDING)
        staff = await make_staff(hospital, "key90-unapproved", ["staff"])

        response = await self.issue(guide, staff)

        assert response.status_code == 409
        assert response.json()["code"] == "GUIDE_NOT_APPROVED"
        assert await PatientGuideLink.all().count() == 0

    async def test_other_hospital_guide_is_hidden(self) -> None:
        owner = await make_hospital("KEY-90 소유 합성의원")
        outsider = await make_hospital("KEY-90 외부 합성의원")
        guide = await make_guide(owner, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(outsider, "key90-outsider", ["staff"])

        response = await self.issue(guide, staff)

        assert response.status_code == 404
        assert response.json()["code"] == "GUIDE_NOT_FOUND"

    async def test_admin_only_account_cannot_issue_a_patient_link(self) -> None:
        hospital = await make_hospital("KEY-90 권한 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        admin = await make_staff(hospital, "key90-admin", ["admin"])

        response = await self.issue(guide, admin)

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    async def test_invalid_and_expired_tokens_are_distinguished_without_exposing_a_guide(self) -> None:
        hospital = await make_hospital("KEY-90 만료 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key90-expired", ["staff"])
        assert (await self.issue(guide, staff)).status_code == 201

        link = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        link.expires_at = now() - timedelta(seconds=1)
        await link.save(update_fields=["expires_at"])

        async with self.client() as client:
            invalid = await client.get("/api/v1/guides/not-a-real-token")
            expired = await client.get(f"/api/v1/guides/{TOKEN}")

        assert invalid.status_code == 404
        assert invalid.json()["code"] == "LINK_NOT_FOUND"
        assert expired.status_code == 410
        assert expired.json()["code"] == "LINK_EXPIRED"
