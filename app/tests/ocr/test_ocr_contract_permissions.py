"""OCR API의 응답 계약과 병원 경계를 실제 로그인·DB 경로로 검증한다 — KEY-61."""

from datetime import UTC, date, datetime

from app.models.ocr import (
    OcrDocumentText,
    OcrDocumentType,
    OcrField,
    OcrFieldCandidate,
    OcrJob,
    OcrJobStatus,
    OcrResult,
)
from app.models.patients import Patient
from app.models.staffs import Staff
from app.models.visits import Visit
from app.tests.ocr.test_ocr_auth_wiring import OcrAuthWiringTestCase


class OcrContractTestCase(OcrAuthWiringTestCase):
    async def make_visit(self, staff: Staff, suffix: str) -> Visit:
        patient = await Patient.create(
            hospital_id=staff.hospital_id,
            hospital_patient_no=f"SYN-KEY61-{suffix}",
            name="합성 환자",
            birth_date=date(2000, 1, 1),
            phone="01000000000",
        )
        return await Visit.create(
            hospital_id=staff.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
        )

    async def make_completed_result(
        self,
        staff: Staff,
        *,
        job_id: str,
    ) -> tuple[OcrJob, OcrField, OcrFieldCandidate]:
        visit = await self.make_visit(staff, job_id)
        job = await OcrJob.create(
            ocr_job_id=job_id,
            hospital_id=staff.hospital_id,
            visit=visit,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
            progress=100,
            started_at=datetime(2026, 8, 24, 9, 1, tzinfo=UTC),
            completed_at=datetime(2026, 8, 24, 9, 2, tzinfo=UTC),
        )
        result = await OcrResult.create(
            ocr_job=job,
            model_name="synthetic-key61-model",
            model_version="1.0",
        )
        document = await OcrDocumentText.create(
            ocr_result=result,
            document_id=610001,
            document_type=OcrDocumentType.LAB_RESULT,
            raw_text="synthetic OCR text; not real patient data",
        )
        field = await OcrField.create(
            ocr_result=result,
            document_text=document,
            field_type="FASTING_GLUCOSE",
            extracted_value="101",
            unit="mg/dL",
            confidence="0.6200",
            source_line=3,
        )
        candidate = await OcrFieldCandidate.create(
            ocr_field=field,
            document_text=document,
            candidate_value="100",
            confidence="0.9100",
            rank=1,
            source_line=3,
        )
        return job, field, candidate


class TestOcrResultStateContracts(OcrContractTestCase):
    async def test_processing_job_has_status_but_no_result_or_fields(self) -> None:
        staff = await self.make_staff(login_id="key61processing", roles=["staff"], hospital_name="알파의원")
        visit = await self.make_visit(staff, "PROCESSING")
        job = await OcrJob.create(
            ocr_job_id="syn-key61-processing",
            hospital_id=staff.hospital_id,
            visit=visit,
            requested_by=staff.staff_id,
            status=OcrJobStatus.PROCESSING,
            progress=42,
            started_at=datetime(2026, 8, 24, 9, 1, tzinfo=UTC),
        )
        token = await self.login(staff.login_id)

        status_response = await self.get(f"/ocr/jobs/{job.ocr_job_id}", token)
        result_response = await self.get(f"/ocr/jobs/{job.ocr_job_id}/result", token)
        fields_response = await self.get(f"/ocr/jobs/{job.ocr_job_id}/fields", token)

        assert status_response.status_code == 200
        assert status_response.json() == {
            "ocr_job_id": job.ocr_job_id,
            "status": "PROCESSING",
            "progress": 42,
            "started_at": "2026-08-24T18:01:00+09:00",
            "completed_at": None,
            "failure_code": None,
            "excluded_from_guide": False,
        }
        for response in (result_response, fields_response):
            assert response.status_code == 409
            assert response.json()["code"] == "OCR_RESULT_NOT_READY"

    async def test_completed_job_without_result_is_not_found(self) -> None:
        staff = await self.make_staff(login_id="key61missing", roles=["staff"], hospital_name="알파의원")
        visit = await self.make_visit(staff, "MISSING")
        job = await OcrJob.create(
            ocr_job_id="syn-key61-missing-result",
            hospital_id=staff.hospital_id,
            visit=visit,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
            progress=100,
        )

        response = await self.get(f"/ocr/jobs/{job.ocr_job_id}/result", await self.login(staff.login_id))

        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"


class TestOcrSuccessAndUpdateContracts(OcrContractTestCase):
    async def test_result_fields_and_successful_update_contract(self) -> None:
        staff = await self.make_staff(login_id="key61success", roles=["staff"], hospital_name="알파의원")
        job, field, candidate = await self.make_completed_result(staff, job_id="syn-key61-success")
        token = await self.login(staff.login_id)

        result_response = await self.get(f"/ocr/jobs/{job.ocr_job_id}/result", token)
        fields_response = await self.get(f"/ocr/jobs/{job.ocr_job_id}/fields?field_type=FASTING_GLUCOSE", token)
        update_response = await self.request(
            "PATCH",
            f"/ocr/fields/{field.ocr_field_id}",
            token,
            json={"base_version": 1, "candidate_id": candidate.ocr_field_candidate_id, "confirm": True},
        )

        assert result_response.status_code == 200
        assert result_response.headers["cache-control"] == "no-store"
        result = result_response.json()
        assert set(result) == {
            "ocr_result_id",
            "ocr_job_id",
            "model_name",
            "model_version",
            "version",
            "confirmed_by",
            "confirmed_at",
            "documents",
            "fields",
        }
        assert result["ocr_job_id"] == job.ocr_job_id
        assert result["documents"][0]["raw_text"] == "synthetic OCR text; not real patient data"
        assert result["fields"][0]["is_low_confidence"] is True
        assert fields_response.status_code == 200
        assert [item["field_type"] for item in fields_response.json()] == ["FASTING_GLUCOSE"]

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["value"] == "100"
        assert updated["corrected_value"] == "100"
        assert updated["version"] == 2
        assert updated["is_confirmed"] is True
        assert updated["modified_by"] == staff.staff_id
        assert updated["confirmed_by"] == staff.staff_id

    async def test_stale_update_is_rejected_without_changing_the_field(self) -> None:
        staff = await self.make_staff(login_id="key61conflict", roles=["staff"], hospital_name="알파의원")
        _, field, _ = await self.make_completed_result(staff, job_id="syn-key61-conflict")
        token = await self.login(staff.login_id)

        first_update = await self.request(
            "PATCH",
            f"/ocr/fields/{field.ocr_field_id}",
            token,
            json={"base_version": 1, "corrected_value": "102"},
        )
        response = await self.request(
            "PATCH",
            f"/ocr/fields/{field.ocr_field_id}",
            token,
            json={"base_version": 1, "corrected_value": "999"},
        )

        assert first_update.status_code == 200
        assert first_update.json()["version"] == 2
        assert response.status_code == 409
        assert response.json()["code"] == "VERSION_CONFLICT"
        await field.refresh_from_db()
        assert field.corrected_value == "102"
        assert field.version == 2


class TestOcrHospitalBoundary(OcrContractTestCase):
    async def test_other_hospital_cannot_read_or_update_any_job_resource(self) -> None:
        owner = await self.make_staff(login_id="key61owner", roles=["staff"], hospital_name="알파의원")
        outsider = await self.make_staff(login_id="key61outsider", roles=["staff"], hospital_name="베타의원")
        job, field, _ = await self.make_completed_result(owner, job_id="syn-key61-private")
        token = await self.login(outsider.login_id)

        responses = [
            await self.get(f"/ocr/jobs/{job.ocr_job_id}", token),
            await self.get(f"/ocr/jobs/{job.ocr_job_id}/result", token),
            await self.get(f"/ocr/jobs/{job.ocr_job_id}/fields", token),
            await self.request(
                "PATCH",
                f"/ocr/fields/{field.ocr_field_id}",
                token,
                json={"base_version": 1, "corrected_value": "attempted overwrite"},
            ),
        ]

        for response in responses:
            assert response.status_code == 404
            assert response.json()["code"] == "NOT_FOUND"
            assert job.ocr_job_id not in response.text
            assert "synthetic OCR text" not in response.text
            assert "101" not in response.text

        await field.refresh_from_db()
        assert field.corrected_value is None
        assert field.version == 1
