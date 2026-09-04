"""환자 경로가 원문·내부 메타데이터·미승인 안내를 내보내지 않는가 — KEY-94."""

from pydantic import BaseModel

from app.dtos.checkins import CheckInAnswerContent, CheckInPainTypeResponse, CheckInReadResponse
from app.dtos.patient_links import (
    PatientCareBlockResponse,
    PatientCareResponse,
    PatientChatResponse,
    PatientGuideDetailResponse,
    PatientGuideDrugResponse,
    PatientGuideGoalResponse,
    PatientGuideResponse,
    PatientGuideSectionResponse,
    PatientLifeAxisResponse,
    PatientLifeResponse,
    PatientMedicationStatResponse,
)
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink
from app.tests.patient_links.test_patient_links import (
    TOKEN,
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

GUIDE_FIELDS = {
    "version",
    "approved_at",
    "expires_at",
    "sections",
    "visit",
    "clinic",
    # OTP 인증한 뷰어에게만 실린다(KEY-268). 인증 전 응답에는 없다.
    "patient_name",
    "disease",
    "stat",
    "guide",
    "care",
    "life",
    "chat",
    "demo_only",
}
GUIDE_REQUIRED_FIELDS = {"version", "approved_at", "expires_at", "sections", "demo_only"}
GUIDE_SECTION_FIELDS = {"key", "body"}
STAT_FIELDS = {"drugName", "drugSub", "prescribed", "dayOn", "remaining", "pct", "out", "why"}
GUIDE_DETAIL_FIELDS = {"summary", "goals", "goalSay", "drug", "why", "how", "next"}
GUIDE_GOAL_FIELDS = {"n", "a", "now", "t", "hasChart", "rangeLabel"}
GUIDE_DRUG_FIELDS = {"n", "s", "d"}
CARE_FIELDS = {"title", "blocks", "danger", "ask"}
CARE_BLOCK_FIELDS = {"t", "p"}
LIFE_FIELDS = {"sub", "challenges", "axes"}
LIFE_AXIS_FIELDS = {"chal", "goal", "title", "p"}
CHAT_FIELDS = {"chips"}
CHECKIN_FIELDS = {
    "round_label",
    "drug_name",
    "answers",
    "pain_types",
    "next_checkin",
    "next_visit",
    "answered",
    "demo_only",
}
CHECKIN_ANSWER_FIELDS = {"lead", "body", "ask", "notify"}
PAIN_TYPE_FIELDS = {"key", "label"}


def _serialized_fields(model: type[BaseModel]) -> set[str]:
    return {field.serialization_alias or name for name, field in model.model_fields.items()}


def test_patient_response_contracts_allow_only_reviewed_fields() -> None:
    """원문·문서 ID·승인자 필드가 DTO에 추가되는 순간 실패한다."""

    assert _serialized_fields(PatientGuideResponse) == GUIDE_FIELDS
    assert _serialized_fields(PatientGuideSectionResponse) == GUIDE_SECTION_FIELDS
    assert _serialized_fields(PatientMedicationStatResponse) == STAT_FIELDS
    assert _serialized_fields(PatientGuideDetailResponse) == GUIDE_DETAIL_FIELDS
    assert _serialized_fields(PatientGuideGoalResponse) == GUIDE_GOAL_FIELDS
    assert _serialized_fields(PatientGuideDrugResponse) == GUIDE_DRUG_FIELDS
    assert _serialized_fields(PatientCareResponse) == CARE_FIELDS
    assert _serialized_fields(PatientCareBlockResponse) == CARE_BLOCK_FIELDS
    assert _serialized_fields(PatientLifeResponse) == LIFE_FIELDS
    assert _serialized_fields(PatientLifeAxisResponse) == LIFE_AXIS_FIELDS
    assert _serialized_fields(PatientChatResponse) == CHAT_FIELDS
    assert set(CheckInReadResponse.model_fields) == CHECKIN_FIELDS
    assert set(CheckInAnswerContent.model_fields) == CHECKIN_ANSWER_FIELDS
    assert set(CheckInPainTypeResponse.model_fields) == PAIN_TYPE_FIELDS


class TestPatientContentBoundaries(PatientLinkTestCase):
    async def test_approved_guide_and_checkin_serialize_only_the_public_contract(self) -> None:
        hospital = await make_hospital("KEY-94 공개 계약 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key94-staff", ["staff"])

        issued = await self.issue(guide, staff)
        assert issued.status_code == 201

        async with self.client() as client:
            patient_guide = await client.get(f"/api/v1/guides/{TOKEN}")
            checkin = await client.get(f"/api/v1/checkins/{TOKEN}")

        assert patient_guide.status_code == 200
        guide_body = patient_guide.json()
        assert GUIDE_REQUIRED_FIELDS <= set(guide_body) <= GUIDE_FIELDS
        assert guide_body["sections"] == [{"key": "medication", "body": "합성 승인 복약 안내"}]
        assert all(set(section) == GUIDE_SECTION_FIELDS for section in guide_body["sections"])

        assert checkin.status_code == 200
        checkin_body = checkin.json()
        assert set(checkin_body) == CHECKIN_FIELDS
        assert all(
            answer is None or set(answer) == CHECKIN_ANSWER_FIELDS for answer in checkin_body["answers"].values()
        )
        assert all(set(pain_type) == PAIN_TYPE_FIELDS for pain_type in checkin_body["pain_types"])

    async def test_approval_pending_guide_cannot_create_a_patient_link(self) -> None:
        """실제 도달 가능한 미승인 상태는 환자용 진입점 자체를 만들지 않는다."""

        hospital = await make_hospital("KEY-94 미승인 차단 합성의원")
        guide = await make_guide(hospital, GuideStatus.APPROVAL_PENDING)
        staff = await make_staff(hospital, "key94-pending", ["doctor"])

        response = await self.issue(guide, staff)

        assert response.status_code == 409
        assert response.json() == {
            "code": "GUIDE_NOT_APPROVED",
            "message": "승인 완료된 안내문만 링크를 발급할 수 있습니다.",
        }
        assert await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).count() == 0

    async def test_stale_approved_at_does_not_open_a_pending_guide(self) -> None:
        """상태가 미승인이면 승인 시각이 남아 있어도 발급·조회 관문이 모두 닫힌다."""

        hospital = await make_hospital("KEY-94 오래된 승인시각 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key94-stale-approved-at", ["doctor"])
        assert (await self.issue(guide, staff)).status_code == 201

        await GuideDocument.filter(guide_document_id=guide.guide_document_id).update(
            status=GuideStatus.APPROVAL_PENDING
        )

        reissued = await self.issue(guide, staff)
        assert reissued.status_code == 409
        assert reissued.json()["code"] == "GUIDE_NOT_APPROVED"

        async with self.client() as client:
            patient_guide = await client.get(f"/api/v1/guides/{TOKEN}")
            checkin = await client.get(f"/api/v1/checkins/{TOKEN}")

        for response in (patient_guide, checkin):
            assert response.status_code == 404
            assert response.json()["code"] == "LINK_NOT_FOUND"

    async def test_missing_approved_at_does_not_open_a_scheduled_guide(self) -> None:
        """상태가 승인 완료여도 승인 시각이 없으면 발급·조회 관문이 모두 닫힌다."""

        hospital = await make_hospital("KEY-94 승인시각 누락 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key94-missing-approved-at", ["doctor"])
        assert (await self.issue(guide, staff)).status_code == 201

        await GuideDocument.filter(guide_document_id=guide.guide_document_id).update(approved_at=None)

        reissued = await self.issue(guide, staff)
        assert reissued.status_code == 409
        assert reissued.json()["code"] == "GUIDE_NOT_APPROVED"

        async with self.client() as client:
            patient_guide = await client.get(f"/api/v1/guides/{TOKEN}")
            checkin = await client.get(f"/api/v1/checkins/{TOKEN}")

        for response in (patient_guide, checkin):
            assert response.status_code == 404
            assert response.json()["code"] == "LINK_NOT_FOUND"
