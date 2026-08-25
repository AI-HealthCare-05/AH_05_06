"""환자 경로가 OCR 원문과 미승인 안내를 내보내지 않는가 — KEY-94."""

from app.models.ocr import OcrDocumentText, OcrDocumentType, OcrJob, OcrJobStatus, OcrResult
from app.models.visits import GuideDocument, GuideSection, GuideStatus
from app.tests.patient_links.test_patient_links import (
    TOKEN,
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

OCR_RAW_SENTINEL = "KEY94_SYNTHETIC_OCR_RAW_MUST_NEVER_REACH_PATIENT"
UNAPPROVED_SENTINEL = "KEY94_SYNTHETIC_UNAPPROVED_BODY_MUST_STAY_HIDDEN"


async def attach_ocr_raw_text(guide) -> None:
    job = await OcrJob.create(
        ocr_job_id="key94-synthetic-ocr-job",
        hospital_id=guide.hospital_id,
        visit_id=guide.visit_id,
        status=OcrJobStatus.COMPLETED,
        progress=100,
        requested_by=1,
    )
    result = await OcrResult.create(
        ocr_job=job,
        model_name="key94-synthetic-model",
        model_version="test-only",
    )
    await OcrDocumentText.create(
        ocr_result=result,
        document_id=94001,
        document_type=OcrDocumentType.PRESCRIPTION,
        raw_text=OCR_RAW_SENTINEL,
    )


class TestPatientContentBoundaries(PatientLinkTestCase):
    async def test_patient_guide_and_checkin_never_serialize_stored_ocr_raw_text(self) -> None:
        hospital = await make_hospital("KEY-94 원문 차단 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key94-staff", ["staff"])
        await attach_ocr_raw_text(guide)

        issued = await self.issue(guide, staff)
        assert issued.status_code == 201

        async with self.client() as client:
            patient_guide = await client.get(f"/api/v1/guides/{TOKEN}")
            checkin = await client.get(f"/api/v1/checkins/{TOKEN}")

        assert patient_guide.status_code == 200
        assert checkin.status_code == 200
        assert "합성 승인 복약 안내" in patient_guide.text
        assert "합성 승인 복약 안내" in checkin.text
        for response in (patient_guide, checkin):
            assert OCR_RAW_SENTINEL not in response.text
            assert "raw_text" not in response.text
            assert "document_id" not in response.text
            assert "합성 생성 원문" not in response.text
            assert "내부 검수용 경고" not in response.text

    async def test_revoked_approval_hides_the_guide_and_checkin_even_with_an_existing_link(self) -> None:
        hospital = await make_hospital("KEY-94 미승인 차단 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key94-revoked", ["doctor"])
        issued = await self.issue(guide, staff)
        assert issued.status_code == 201

        section = await GuideSection.get(guide_document_id=guide.guide_document_id)
        section.edited_body = UNAPPROVED_SENTINEL
        await section.save(update_fields=["edited_body"])
        await GuideDocument.filter(guide_document_id=guide.guide_document_id).update(
            status=GuideStatus.APPROVAL_RETURNED,
            approved_at=None,
        )

        async with self.client() as client:
            patient_guide = await client.get(f"/api/v1/guides/{TOKEN}")
            checkin = await client.get(f"/api/v1/checkins/{TOKEN}")

        for response in (patient_guide, checkin):
            assert response.status_code == 404
            assert response.json()["code"] == "LINK_NOT_FOUND"
            assert UNAPPROVED_SENTINEL not in response.text
