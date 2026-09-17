"""KEY-239 patient-session feedback submission contract."""

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient, Response
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError
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

    async def approved(
        self, name: str = "KEY-239 합성의원", *, status: GuideStatus = GuideStatus.SCHEDULED_TO_SEND
    ) -> GuideDocument:
        hospital = await make_hospital(name)
        guide = await make_guide(hospital, status)
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
            expires_at=now().replace(year=now().year + 1),
            issued_by=1,
        )
        return guide

    async def with_expired_link(self, name: str = "KEY-239 합성의원") -> GuideDocument:
        hospital = await make_hospital(name)
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
            expires_at=now().replace(year=now().year - 1),
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

    async def test_chatbot_feedback_from_p9_is_rejected(self) -> None:
        await self.approved()
        payload = {
            "submission_id": str(uuid4()),
            "target": "CHATBOT_RESPONSE",
            "source_screen": "P9",
            "category": "HELPFUL",
            "response_ref": RESPONSE_REF,
        }

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"
        assert await PatientFeedback.all().count() == 0

    async def test_guide_feedback_from_p6_is_rejected(self) -> None:
        await self.approved()
        payload = {
            **self.guide_payload(),
            "source_screen": "P6",
        }

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"
        assert await PatientFeedback.all().count() == 0

    async def test_expired_link_is_rejected(self) -> None:
        """만료된 링크 — KEY-361 인수조건. 세션 자체는 유효해도, 그 세션이
        가리키는 링크가 만료됐으면 피드백을 저장할 안내를 못 찾는다."""
        await self.with_expired_link()

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=self.guide_payload())

        assert response.status_code == 404
        assert response.json()["code"] == "FEEDBACK_CONTEXT_NOT_FOUND"
        assert await PatientFeedback.all().count() == 0

    async def test_unapproved_guide_is_rejected(self) -> None:
        """미승인 안내문 — KEY-361 인수조건. 링크는 살아있어도 안내가
        아직 SCHEDULED_TO_SEND가 아니면(승인 전) 저장하지 않는다."""
        await self.approved(status=GuideStatus.STAFF_REVIEW)

        async with await self.client() as client:
            response = await client.post("/api/v1/patient-feedback", json=self.guide_payload())

        assert response.status_code == 404
        assert response.json()["code"] == "FEEDBACK_CONTEXT_NOT_FOUND"
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

    async def test_all_clinic_roles_only_see_feedback_from_their_hospital(self) -> None:
        own = await self.feedback("KEY-239 목록 기준병원", details="합성 상세")
        await self.feedback("KEY-239 목록 타병원", details="타 병원 상세")

        for user_id, role in enumerate(("staff", "doctor", "admin"), start=239):
            actor = StaffActor(user_id=user_id, hospital_id=own.hospital_id, roles=frozenset({role}))
            response = await self.request_as(actor)

            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["feedback_id"] == own.patient_feedback_id
            assert body["items"][0]["has_details"] is True
            assert "details" not in body["items"][0]

    async def test_all_clinic_roles_can_read_detail_inside_their_hospital(self) -> None:
        own = await self.feedback("KEY-239 상세 기준병원", details="합성 상세 내용")

        for user_id, role in enumerate(("staff", "doctor", "admin"), start=242):
            actor = StaffActor(user_id=user_id, hospital_id=own.hospital_id, roles=frozenset({role}))
            app.dependency_overrides[get_staff_actor] = lambda actor=actor: actor

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

        for user_id, role in enumerate(("staff", "doctor", "admin"), start=245):
            actor = StaffActor(user_id=user_id, hospital_id=other.hospital_id + 1, roles=frozenset({role}))
            app.dependency_overrides[get_staff_actor] = lambda actor=actor: actor

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(f"/api/v1/admin/patient-feedback/{other.patient_feedback_id}")

            assert response.status_code == 404
            assert response.json()["code"] == "PATIENT_FEEDBACK_NOT_FOUND"


class TestTwoSubmissionsThatLandTogether(PatientFeedbackApiTestCase):
    """`except IntegrityError` 가지 — **읽은 뒤 `create` 사이**에 남이 먼저 넣은 자리.

    KEY-346 에서 재 보니 이 가지가 **한 번도 안 돌고 있었다.** 복구를 통째로
    걷어내고 `raise` 로 바꿔도 `patient_feedback`·`models`·`patient_usage` 의
    59 개가 전부 통과했다. 위의 `test_network_retry_returns_the_same_row` 는
    순차라 `create()` 의 **첫 읽기**에서 이미 걸린다.

    `#310`(KEY-335) 리뷰에서 이희진 님이 체크인 쪽에 같은 것을 짚으셨고, 거기만
    메워졌다. 원형인 이쪽이 비어 있었다.

    **진짜 동시 요청은 이 하네스에서 못 만든다** — 검사를 트랜잭션으로 감싸고
    커넥션 하나를 공유해서, `asyncio.gather` 로 둘을 보내면 MySQL 소켓이 먼저
    깨진다(`#50`·KEY-328 에서 확인된 자리).

    그래서 **겹치는 순간만** 만든다. `create` 직전에 다른 요청이 먼저 넣은 것처럼
    진짜 줄을 하나 만들고, 원래 `create` 가 그대로 돌게 둔다. `IntegrityError`
    를 흉내내지 않는다 — **DB 의 유일 제약이** 막는 것까지 함께 잰다.
    """

    @staticmethod
    def _another_request_wins(**overrides: Any) -> Callable[..., Awaitable[PatientFeedback]]:
        original = PatientFeedback.create

        async def create(**kwargs: Any) -> PatientFeedback:
            await original(**{**kwargs, **overrides})  # 남이 먼저 넣는다
            return await original(**kwargs)  # 원래 요청이 유일 제약에 부딪힌다

        return create

    async def test_the_same_submission_arriving_twice_at_once_still_succeeds(self) -> None:
        await self.approved()
        payload = self.guide_payload(str(uuid4()))

        with patch.object(PatientFeedback, "create", self._another_request_wins()):
            async with await self.client() as client:
                response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 201, response.text
        assert await PatientFeedback.all().count() == 1, "경합에서 줄이 둘 생겼다"
        stored = await PatientFeedback.all().first()
        assert stored is not None
        assert response.json()["feedback_id"] == stored.patient_feedback_id, "먼저 들어간 줄을 안 돌려줬다"

    async def test_a_different_submission_arriving_at_once_is_still_blocked(self) -> None:
        """같은 열쇠에 **다른 내용**이면 조용히 덮지 않는다."""
        await self.approved()
        payload = self.guide_payload(str(uuid4()))

        with patch.object(PatientFeedback, "create", self._another_request_wins(category="UNSAFE")):
            async with await self.client() as client:
                response = await client.post("/api/v1/patient-feedback", json=payload)

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "FEEDBACK_SUBMISSION_CONFLICT"
        stored = await PatientFeedback.all().first()
        assert stored is not None
        assert stored.category == "UNSAFE", "먼저 저장된 값이 덮였다"

    async def test_an_integrity_error_with_nothing_to_re_read_is_not_swallowed(self) -> None:
        """🚩 `if existing is None: raise` 자리.

        유일 제약이 아닌 다른 까닭(예: FK 위반)으로 `IntegrityError` 가 나면
        **다시 읽어도 아무것도 없다.** 그때 이 가지가 조용히 삼키면, 저장이 안
        된 것이 성공으로 보인다.
        """
        await self.approved()
        payload = self.guide_payload(str(uuid4()))

        async def create(**_: Any) -> PatientFeedback:
            raise IntegrityError("다른 까닭으로 막혔다")

        # `ASGITransport` 는 앱에서 올라온 예외를 **그대로 다시 던진다.** 그래서
        # 여기서 `IntegrityError` 가 잡히는 것 자체가 「안 삼켰다」의 증거다.
        # 삼키면 `201` 이 돌아오고 — 저장이 안 됐는데 성공으로 보인다.
        with patch.object(PatientFeedback, "create", create):
            with self.assertRaises(IntegrityError):
                async with await self.client() as client:
                    await client.post("/api/v1/patient-feedback", json=payload)

        assert await PatientFeedback.all().count() == 0, "실패했는데 줄이 남았다"
