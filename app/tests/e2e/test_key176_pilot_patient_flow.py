"""OTP부터 챗봇·D+7 환류까지 Pilot 경계를 한 번에 검증한다 — KEY-176."""

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.timezone import now

from app.apis.v1.chatbot_routers import get_chatbot_service
from app.apis.v1.patient_otp_routers import _otp_service
from app.main import app
from app.models.staffs import Hospital
from app.models.visits import (
    CheckIn,
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientAnswerOutcome,
    PatientGuideLink,
    PatientOtpChallenge,
    PatientUsageEvent,
    PatientUsageEventType,
)
from app.services.chatbot import ChatbotService, ChatModelError, ModelAnswer
from app.services.patient_otp import OTP_RESEND_COOLDOWN, PatientOtpService
from app.services.staff_auth import StaffSessionService
from app.tests.auth_base import AuthTestCase
from app.tests.patient_links.test_patient_links import make_guide, make_hospital, make_staff
from app.tests.patient_links.test_patient_otp import RecordingDelivery

LINK_TOKEN = "synthetic-key176-link-token-never-used-outside-tests"
OTHER_LINK_TOKEN = "synthetic-key176-other-hospital-token"
OTP = "176176"
REAUTH_OTP = "176177"
OTP_SECRET = "synthetic-key176-otp-secret-never-used-outside-tests"
QUESTION = "합성 질문: 약은 언제 먹나요?"
ANSWER = "매일 저녁 같은 시간에 복용하세요."


@dataclass
class FailOnceModel:
    """첫 호출은 외부 장애, 재시도는 승인 문구 안의 답으로 끝낸다."""

    model_name: str = "synthetic-key176-model"
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

    async def generate(self, *, instructions: str, prompt: str) -> ModelAnswer:
        self.calls += 1
        self.prompts.append(f"{instructions}\n{prompt}")
        if self.calls == 1:
            raise ChatModelError("synthetic network failure")
        return ModelAnswer(ANSWER, input_tokens=1, output_tokens=1)


class TestKey176PilotPatientFlow(AuthTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.delivery = RecordingDelivery()
        self.otp = PatientOtpService(self.delivery, secret_key=OTP_SECRET)
        self.model = FailOnceModel()
        app.dependency_overrides[_otp_service] = lambda: self.otp
        app.dependency_overrides[get_chatbot_service] = lambda: ChatbotService(model=self.model)

    async def _approved_link(self, hospital_name: str, token: str) -> GuideDocument:
        hospital = await make_hospital(hospital_name)
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        medication = await GuideSection.get(
            guide_document=guide,
            section_key=GuideSectionKey.MEDICATION,
        )
        medication.edited_body = f"합성 승인 복약 안내: {ANSWER}"
        await medication.save(update_fields=["edited_body"])
        await GuideSection.create(
            guide_document=guide,
            section_key=GuideSectionKey.CAUTION,
            generated_body="합성 승인 주의 안내: 불편하면 담당 병원에 문의하세요.",
        )
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now() + timedelta(hours=72),
            issued_by=1,
        )
        return guide

    async def _authenticate(self, client: AsyncClient, code: str) -> None:
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(code)):
            issued = await client.post(
                "/api/v1/patient-auth/otp/issue",
                json={"link_token": LINK_TOKEN},
            )
        assert issued.status_code == 200, issued.text
        verified = await client.post(
            "/api/v1/patient-auth/otp/verify",
            json={"link_token": LINK_TOKEN, "code": code},
        )
        assert verified.status_code == 200, verified.text

    async def test_failure_reauthentication_retry_and_d7_complete_one_journey(self) -> None:
        guide = await self._approved_link("KEY-176 Pilot 합성의원", LINK_TOKEN)
        other = await self._approved_link("KEY-176 타 병원 합성의원", OTHER_LINK_TOKEN)
        other_section = await GuideSection.get(
            guide_document=other,
            section_key=GuideSectionKey.MEDICATION,
        )
        other_section.edited_body = "타 병원의 컨텍스트는 절대 포함되면 안 됩니다."
        await other_section.save(update_fields=["edited_body"])
        hospital = await Hospital.get(hospital_id=guide.hospital_id)
        staff = await make_staff(hospital, "key176-staff", ["staff"])
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        staff_headers = {"Authorization": f"Bearer {access}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as patient:
            await self._authenticate(patient, OTP)

            opened = await patient.get(f"/api/v1/guides/{LINK_TOKEN}")
            assert opened.status_code == 200, opened.text

            failed = await patient.post(
                "/api/v1/chatbot/responses",
                json={"link_token": LINK_TOKEN, "question": QUESTION},
            )
            retried = await patient.post(
                "/api/v1/chatbot/responses",
                json={"link_token": LINK_TOKEN, "question": QUESTION},
            )
            assert failed.status_code == retried.status_code == 200
            assert failed.json()["fallback"] is True
            assert retried.json()["fallback"] is False
            assert self.model.calls == 2
            assert all("타 병원의 컨텍스트" not in prompt for prompt in self.model.prompts)

            for key in list(self.redis.values):
                if key.startswith("patient_session:"):
                    await self.redis.delete(key)
            expired = await patient.post(
                f"/api/v1/checkins/{LINK_TOKEN}",
                json={"medication": "taking", "pain": {"had": False}},
            )
            assert expired.status_code == 401
            assert expired.json()["code"] == "PATIENT_SESSION_EXPIRED"
            assert await CheckIn.all().count() == 0

            challenge = await PatientOtpChallenge.get()
            challenge.issued_at = now() - OTP_RESEND_COOLDOWN - timedelta(seconds=1)
            await challenge.save(update_fields=["issued_at"])
            await self._authenticate(patient, REAUTH_OTP)
            submitted = await patient.post(
                f"/api/v1/checkins/{LINK_TOKEN}",
                json={"medication": "taking", "pain": {"had": False}},
            )
            assert submitted.status_code == 201, submitted.text

            hospital_read = await patient.get(
                f"/api/v1/visits/{guide.visit_id}/checkin",
                headers=staff_headers,
            )
            assert hospital_read.status_code == 200, hospital_read.text
            assert hospital_read.json()["visit_id"] == guide.visit_id

        events = await PatientUsageEvent.filter(guide_document=guide).order_by("patient_usage_event_id")
        assert [event.event_type for event in events] == [
            PatientUsageEventType.GUIDE_VIEWED,
            PatientUsageEventType.CHATBOT_ANSWERED,
            PatientUsageEventType.CHATBOT_ANSWERED,
        ]
        assert [event.answer_outcome for event in events[1:]] == [
            PatientAnswerOutcome.FALLBACK,
            PatientAnswerOutcome.ANSWERED,
        ]
        stored = repr([event.__dict__ for event in events])
        for raw_value in (LINK_TOKEN, QUESTION, ANSWER):
            assert raw_value not in stored
        assert await PatientUsageEvent.filter(guide_document=other).count() == 0

    async def test_unapproved_link_never_reaches_otp_chatbot_or_usage_events(self) -> None:
        hospital = await make_hospital("KEY-176 미승인 Pilot 합성의원")
        guide = await make_guide(hospital, GuideStatus.APPROVAL_PENDING)
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=hashlib.sha256(LINK_TOKEN.encode()).hexdigest(),
            expires_at=now() + timedelta(hours=72),
            issued_by=1,
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as patient:
            otp = await patient.post(
                "/api/v1/patient-auth/otp/issue",
                json={"link_token": LINK_TOKEN},
            )
            chatbot = await patient.post(
                "/api/v1/chatbot/responses",
                json={"link_token": LINK_TOKEN, "question": QUESTION},
            )

        assert otp.status_code == 404
        assert chatbot.status_code == 404
        assert self.delivery.sent == []
        assert self.model.calls == 0
        assert await PatientUsageEvent.all().count() == 0
