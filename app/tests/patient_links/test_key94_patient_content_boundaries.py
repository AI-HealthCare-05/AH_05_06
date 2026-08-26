"""환자 경로가 원문·내부 메타데이터·미승인 안내를 내보내지 않는가 — KEY-94."""

from app.dtos.checkins import CheckInAnswerContent, CheckInPainTypeResponse, CheckInReadResponse
from app.dtos.patient_links import PatientGuideResponse, PatientGuideSectionResponse
from app.models.visits import GuideStatus, PatientGuideLink
from app.tests.patient_links.test_patient_links import (
    TOKEN,
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

GUIDE_FIELDS = {"version", "approved_at", "expires_at", "sections", "demo_only"}
GUIDE_SECTION_FIELDS = {"key", "body"}
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


def test_patient_response_contracts_allow_only_reviewed_fields() -> None:
    """원문·문서 ID·승인자 필드가 DTO에 추가되는 순간 실패한다."""

    assert set(PatientGuideResponse.model_fields) == GUIDE_FIELDS
    assert set(PatientGuideSectionResponse.model_fields) == GUIDE_SECTION_FIELDS
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
        assert set(guide_body) == GUIDE_FIELDS
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
