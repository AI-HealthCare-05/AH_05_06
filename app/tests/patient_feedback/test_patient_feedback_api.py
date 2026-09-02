"""KEY-239 patient-session feedback submission contract."""

import hashlib
from uuid import uuid4

from httpx import ASGITransport, AsyncClient, Response
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.redis_client import get_redis
from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.main import app
from app.models.feedback import PatientFeedback
from app.models.visits import (
    GuideDocument,
    GuideStatus,
    PatientAnswerOutcome,
    PatientGuideLink,
    PatientQuestionKind,
    PatientUsageEvent,
    PatientUsageEventType,
)
from app.services.patient_sessions import PatientSessionStore
from app.tests.fakes import FakeRedis
from app.tests.patient_links.test_patient_links import TOKEN, make_guide, make_hospital

RESPONSE_REF = "synthetic-response-reference-239"


class PatientFeedbackApiTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def approved(self, name: str = "KEY-239 합성의원") -> GuideDocument:
        hospital = await make_hospital(name)
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
            expires_at=now().replace(year=now().year + 1),
            issued_by=1,
        )
        return guide

    async def client(self, *, authenticated: bool = True) -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        if authenticated:
            raw_session = await PatientSessionStore(self.redis).start(TOKEN)  # type: ignore[arg-type]
            client.cookies.set("patient_session", raw_session)
        return client

    @staticmethod
    def guide_payload(submission_id: str | None = None) -> dict[str, object]:
        return {
            "submission_id": submission_id or str(uuid4()),
            "target": "GUIDE_SECTION",
            "source_screen": "P9",
            "category": "WRONG",
            "section_key": "medication",
            "content_key": "medication.why",
            "detected_tab": "복약지도",
            "details": "합성 안내 피드백",
        }


class TestGuideFeedbackSubmission(PatientFeedbackApiTestCase):
    async def test_patient_session_stores_scoped_feedback_without_sensitive_values(self) -> None:
        guide = await self.approved()

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=self.guide_payload())

        assert response.status_code == 201
        assert response.json()["saved"] is True
        stored = await PatientFeedback.get(patient_feedback_id=response.json()["feedback_id"])
        assert stored.guide_document_id == guide.guide_document_id
        assert stored.hospital_id == guide.hospital_id
        rendered = repr(stored.__dict__)
        assert TOKEN not in rendered
        assert "patient_session" not in rendered

    async def test_network_retry_returns_the_same_row(self) -> None:
        await self.approved()
        submission_id = str(uuid4())
        payload = self.guide_payload(submission_id)

        async with await self.client() as client:
            first = await client.post("/api/v1/patient-feedback", json=payload)
            retry = await client.post("/api/v1/patient-feedback", json=payload)

        assert first.status_code == retry.status_code == 201
        assert first.json()["feedback_id"] == retry.json()["feedback_id"]
        assert await PatientFeedback.all().count() == 1

    async def test_reusing_submission_id_for_different_content_is_rejected(self) -> None:
        await self.approved()
        submission_id = str(uuid4())
        first_payload = self.guide_payload(submission_id)
        changed_payload = {**first_payload, "category": "UNSAFE"}

        async with await self.client() as client:
            first = await client.post("/api/v1/patient-feedback", json=first_payload)
            changed = await client.post("/api/v1/patient-feedback", json=changed_payload)

        assert first.status_code == 201
        assert changed.status_code == 409
        assert changed.json()["code"] == "FEEDBACK_SUBMISSION_CONFLICT"
        assert await PatientFeedback.all().count() == 1

    async def test_missing_session_is_rejected(self) -> None:
        await self.approved()

        async with await self.client(authenticated=False) as client:
            response = await client.post("/api/v1/patient-feedback", json=self.guide_payload())

        assert response.status_code == 401
        assert response.json()["code"] == "PATIENT_SESSION_EXPIRED"
        assert await PatientFeedback.all().count() == 0

    async def test_link_token_and_unknown_fields_cannot_be_submitted(self) -> None:
        await self.approved()
        payload = {**self.guide_payload(), "link_token": TOKEN}

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"
        assert await PatientFeedback.all().count() == 0

    async def test_details_longer_than_the_contract_is_rejected(self) -> None:
        await self.approved()
        payload = {**self.guide_payload(), "details": "합" * 1001}

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"
        assert await PatientFeedback.all().count() == 0


class TestChatbotFeedbackReference(PatientFeedbackApiTestCase):
    async def test_response_reference_can_only_select_an_event_from_the_session_guide(self) -> None:
        guide = await self.approved()
        event = await PatientUsageEvent.create(
            guide_document=guide,
            event_type=PatientUsageEventType.CHATBOT_ANSWERED,
            question_kind=PatientQuestionKind.MEDICATION,
            answer_outcome=PatientAnswerOutcome.ANSWERED,
            response_ref_digest=hashlib.sha256(RESPONSE_REF.encode()).hexdigest(),
        )
        payload = {
            "submission_id": str(uuid4()),
            "target": "CHATBOT_RESPONSE",
            "source_screen": "P6",
            "category": "HELPFUL",
            "response_ref": RESPONSE_REF,
        }

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 201
        stored = await PatientFeedback.get(patient_feedback_id=response.json()["feedback_id"])
        assert stored.usage_event_id == event.patient_usage_event_id
        assert RESPONSE_REF not in repr(stored.__dict__)

    async def test_unknown_response_reference_is_hidden(self) -> None:
        await self.approved()
        payload = {
            "submission_id": str(uuid4()),
            "target": "CHATBOT_RESPONSE",
            "source_screen": "P6",
            "category": "UNHELPFUL",
            "response_ref": "synthetic-missing-reference-239",
        }

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 404
        assert response.json()["code"] == "FEEDBACK_CONTEXT_NOT_FOUND"
        assert await PatientFeedback.all().count() == 0


class TestAdminFeedbackList(PatientFeedbackApiTestCase):
    async def feedback(self, hospital_name: str, *, details: str | None = None) -> PatientFeedback:
        hospital = await make_hospital(hospital_name)
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        return await PatientFeedback.create(
            hospital_id=hospital.hospital_id,
            guide_document=guide,
            target="GUIDE_SECTION",
            source_screen="P9",
            section_key="medication",
            content_key="medication.why",
            category="WRONG",
            details=details,
            idempotency_digest=hashlib.sha256(f"{hospital_name}-submission".encode()).hexdigest(),
        )

    async def request_as(self, actor: StaffActor) -> Response:
        app.dependency_overrides[get_staff_actor] = lambda: actor
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/v1/admin/patient-feedback")

    async def test_admin_only_sees_feedback_from_their_hospital(self) -> None:
        own = await self.feedback("KEY-239 목록 기준병원", details="합성 상세")
        await self.feedback("KEY-239 목록 타병원", details="타 병원 상세")
        actor = StaffActor(user_id=239, hospital_id=own.hospital_id, roles=frozenset({"admin"}))

        response = await self.request_as(actor)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["feedback_id"] == own.patient_feedback_id
        assert body["items"][0]["has_details"] is True
        assert "details" not in body["items"][0]

    async def test_non_admin_is_forbidden(self) -> None:
        own = await self.feedback("KEY-239 목록 권한병원")
        actor = StaffActor(user_id=240, hospital_id=own.hospital_id, roles=frozenset({"staff"}))

        response = await self.request_as(actor)

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    async def test_admin_can_read_detail_inside_their_hospital(self) -> None:
        own = await self.feedback("KEY-239 상세 기준병원", details="합성 상세 내용")
        actor = StaffActor(user_id=241, hospital_id=own.hospital_id, roles=frozenset({"admin"}))
        app.dependency_overrides[get_staff_actor] = lambda: actor

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/admin/patient-feedback/{own.patient_feedback_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["details"] == "합성 상세 내용"
        assert body["content_key"] == "medication.why"
        assert not {
            "idempotency_digest",
            "response_ref_digest",
            "patient_session",
            "link_token",
            "otp",
        } & set(body)

    async def test_feedback_from_another_hospital_is_hidden(self) -> None:
        other = await self.feedback("KEY-239 상세 타병원", details="타 병원 상세")
        actor = StaffActor(user_id=242, hospital_id=other.hospital_id + 1, roles=frozenset({"admin"}))
        app.dependency_overrides[get_staff_actor] = lambda: actor

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/admin/patient-feedback/{other.patient_feedback_id}")

        assert response.status_code == 404
        assert response.json()["code"] == "PATIENT_FEEDBACK_NOT_FOUND"
