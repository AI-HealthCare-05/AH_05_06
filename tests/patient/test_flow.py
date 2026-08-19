from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.patient.chatbot import ApprovedKnowledgeChatbot
from app.patient.contracts import (
    ApprovalStatus,
    ApprovedGuidanceBundle,
    ApprovedKnowledge,
    GuidanceSection,
    InMemoryApprovedGuidanceProvider,
    KnowledgeKind,
    Medication,
)
from app.patient.messaging import InMemoryPatientMessageGateway, MessageKind
from app.patient.models import AdherenceStatus, LinkState, PainType
from app.patient.security import PatientSecretCodec
from app.patient.service import PatientFlowError, PatientFlowService
from app.patient.store import PatientFlowStore


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


def approved_bundle(encounter_date: date = date(2026, 8, 12)) -> ApprovedGuidanceBundle:
    return ApprovedGuidanceBundle(
        bundle_id="approved-bundle-1",
        care_episode_id="episode-1",
        status=ApprovalStatus.APPROVED,
        approved_at=datetime(2026, 8, 12, 5, 0, tzinfo=UTC),
        clinic_name="여성의원",
        encounter_date=encounter_date,
        patient_display_name="김환자",
        medications=[
            Medication(
                name="비잔정",
                strength="2mg",
                dosage="하루 한 번",
                purpose="통증 관리",
                duration_days=84,
            )
        ],
        medication_guidance=[
            GuidanceSection(id="med-1", title="복용 방법", body="매일 같은 시간에 드세요.", source_label="승인 안내")
        ],
        cautions=[
            GuidanceSection(id="cau-1", title="주의사항", body="임의로 중단하지 마세요.", source_label="승인 안내")
        ],
        lifestyle_guidance=[
            GuidanceSection(id="life-1", title="생활관리", body="규칙적으로 걸어 보세요.", source_label="승인 안내")
        ],
        knowledge=[
            ApprovedKnowledge(
                id="knowledge-1",
                title="복용 시간",
                content="비잔정은 매일 같은 시간에 복용하세요.",
                source_label="의료진 승인 복약안내",
                kind=KnowledgeKind.APPROVED_GUIDANCE,
            )
        ],
    )


@pytest.fixture
def flow_parts():
    clock = MutableClock()
    provider = InMemoryApprovedGuidanceProvider()
    provider.register(approved_bundle())
    gateway = InMemoryPatientMessageGateway()
    store = PatientFlowStore()
    flow = PatientFlowService(
        store=store,
        guidance_provider=provider,
        message_gateway=gateway,
        codec=PatientSecretCodec("test-secret"),
        now=clock,
        public_patient_url="https://patient.test/patient/",
    )
    return flow, clock, gateway, store


async def issue_and_get_token(flow, gateway):
    link = await flow.issue_link("episode-1", "010-1234-5678", date(1990, 1, 1))
    message = gateway.messages[-1]
    assert message.kind is MessageKind.ACCESS_LINK
    return link, message.content.split("#access=", 1)[1]


@pytest.mark.asyncio
async def test_link_expires_after_72_hours(flow_parts):
    flow, clock, gateway, _ = flow_parts
    link, token = await issue_and_get_token(flow, gateway)
    assert link.state is LinkState.SENT
    clock.advance(timedelta(hours=71, minutes=59))
    assert flow.inspect_link(token).id == link.id
    clock.advance(timedelta(minutes=1))
    with pytest.raises(PatientFlowError, match="3일") as error:
        flow.inspect_link(token)
    assert error.value.code == "link_expired"


@pytest.mark.asyncio
async def test_scheduled_link_is_sent_only_when_due_and_expires_72_hours_later(flow_parts):
    flow, clock, gateway, _ = flow_parts
    send_at = clock.value + timedelta(hours=2)
    link = await flow.issue_link("episode-1", "010-1234-5678", date(1990, 1, 1), send_at)
    assert link.state is LinkState.SCHEDULED
    assert gateway.messages == []
    assert await flow.dispatch_due_links() == 0
    clock.advance(timedelta(hours=2))
    assert await flow.dispatch_due_links() == 1
    assert link.state is LinkState.SENT
    assert link.expires_at == send_at + timedelta(hours=72)


@pytest.mark.asyncio
async def test_revoked_link_can_be_reissued_and_old_sessions_are_revoked(flow_parts):
    flow, _, gateway, _ = flow_parts
    old_link, token = await issue_and_get_token(flow, gateway)
    challenge = await flow.request_otp(token)
    otp = gateway.messages[-1].content
    _, raw_session = flow.verify_otp(challenge.id, otp)
    flow.revoke_link(old_link.id)
    with pytest.raises(PatientFlowError) as error:
        flow.authenticate(raw_session)
    assert error.value.code == "reauthentication_required"
    new_link = await flow.reissue_link(token, "01012345678", "900101")
    assert new_link.id != old_link.id
    assert new_link.state is LinkState.SENT


@pytest.mark.asyncio
async def test_otp_locks_after_five_failures(flow_parts):
    flow, _, gateway, _ = flow_parts
    _, token = await issue_and_get_token(flow, gateway)
    challenge = await flow.request_otp(token)
    wrong_code = "000000" if gateway.messages[-1].content != "000000" else "111111"
    for _ in range(4):
        with pytest.raises(PatientFlowError) as error:
            flow.verify_otp(challenge.id, wrong_code)
        assert error.value.code == "otp_mismatch"
    with pytest.raises(PatientFlowError) as error:
        flow.verify_otp(challenge.id, wrong_code)
    assert error.value.code == "otp_locked"
    assert error.value.status_code == 429


@pytest.mark.asyncio
async def test_reissue_identity_fallback_locks_after_five_failures(flow_parts):
    flow, _, gateway, _ = flow_parts
    _, token = await issue_and_get_token(flow, gateway)
    for _ in range(4):
        with pytest.raises(PatientFlowError) as error:
            await flow.reissue_link(token, "01099998888", "900101")
        assert error.value.code == "identity_mismatch"
    with pytest.raises(PatientFlowError) as error:
        await flow.reissue_link(token, "01099998888", "900101")
    assert error.value.code == "fallback_locked"
    assert error.value.status_code == 429
    assert error.value.retry_after_seconds == 600


@pytest.mark.asyncio
async def test_session_expires_after_30_minutes_and_missing_cookie_reauthenticates(flow_parts):
    flow, clock, gateway, _ = flow_parts
    _, token = await issue_and_get_token(flow, gateway)
    challenge = await flow.request_otp(token)
    _, raw_session = flow.verify_otp(challenge.id, gateway.messages[-1].content)
    assert flow.guidance(raw_session).bundle_id == "approved-bundle-1"
    clock.advance(timedelta(minutes=30))
    with pytest.raises(PatientFlowError) as error:
        flow.guidance(raw_session)
    assert error.value.code == "session_expired"
    with pytest.raises(PatientFlowError) as error:
        flow.guidance(None)
    assert error.value.code == "reauthentication_required"


def test_key2_contract_rejects_raw_document_and_draft_status():
    data = approved_bundle().model_dump()
    data["raw_document_url"] = "https://example.test/raw.pdf"
    with pytest.raises(ValidationError):
        ApprovedGuidanceBundle.model_validate(data)
    data.pop("raw_document_url")
    data["status"] = "draft"
    with pytest.raises(ValidationError):
        ApprovedGuidanceBundle.model_validate(data)


def test_chatbot_uses_only_approved_knowledge_and_does_not_store_transcript():
    chatbot = ApprovedKnowledgeChatbot()
    answer = chatbot.answer("비잔정 복용 시간은 언제인가요?", approved_bundle())
    assert "매일 같은 시간" in answer.answer
    assert answer.evidence[0].source_id == "knowledge-1"
    assert "승인" in answer.evidence[0].source_label
    assert not hasattr(chatbot, "messages")


@pytest.mark.asyncio
async def test_d_plus_seven_follow_up_validates_and_saves_structured_response(flow_parts):
    flow, _, gateway, store = flow_parts
    link, token = await issue_and_get_token(flow, gateway)
    challenge = await flow.request_otp(token)
    _, raw_session = flow.verify_otp(challenge.id, gateway.messages[-1].content)
    status = flow.follow_up_status(raw_session)
    assert status["due"] is True
    saved = flow.submit_follow_up(
        raw_session,
        AdherenceStatus.TAKING,
        True,
        4,
        (PainType.DYSMENORRHEA,),
        "오늘 오전",
    )
    assert saved.pain_score == 4
    assert store.follow_ups[link.id] == saved
    assert flow.get_follow_up_for_staff(link.id) == saved
    assert not hasattr(store, "chat_messages")


@pytest.mark.asyncio
async def test_medication_status_is_separate_from_d_plus_seven(flow_parts):
    flow, _, gateway, _ = flow_parts
    _, token = await issue_and_get_token(flow, gateway)
    challenge = await flow.request_otp(token)
    _, raw_session = flow.verify_otp(challenge.id, gateway.messages[-1].content)

    status = flow.medication_status(raw_session)

    assert status["prescription_date"] == date(2026, 8, 12)
    assert status["medications"][0] == {
        "name": "비잔정",
        "strength": "2mg",
        "total_days": 84,
        "elapsed_days": 7,
        "remaining_days": 77,
        "progress_percent": 8,
        "depletion_date": date(2026, 11, 4),
        "purpose": "통증 관리",
    }


@pytest.mark.asyncio
async def test_stopped_selection_notifies_staff_immediately_and_is_idempotent(flow_parts):
    flow, _, gateway, store = flow_parts
    link, token = await issue_and_get_token(flow, gateway)
    challenge = await flow.request_otp(token)
    _, raw_session = flow.verify_otp(challenge.id, gateway.messages[-1].content)

    first = flow.record_adherence_selection(raw_session, AdherenceStatus.STOPPED_BETTER)
    second = flow.record_adherence_selection(raw_session, AdherenceStatus.STOPPED_BETTER)
    missed = flow.record_adherence_selection(raw_session, AdherenceStatus.SOMETIMES_MISSED)

    assert first is second
    assert missed is None
    assert len(store.follow_up_alerts) == 1
    assert first is not None and first.link_id == link.id
