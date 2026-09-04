"""이전 방문 확정 OCR 값 조회 — KEY-246.

같은 환자·같은 병원의 이전 방문에서 확정된 OCR 필드를 field_type별 최신 하나씩
반환하는 엔드포인트를 검증한다.

인수조건:
1. 같은 환자·같은 항목의 가장 최근 확정 OCR 값을 조회하는 경로가 있다.
2. 승인·확정된 값만 사용하고 미확정·타 병원 값은 서버에서 차단한다.
3. 이전 값 없음 / 정상 케이스를 커버한다.
"""

from datetime import UTC, date, datetime

from app.models.ocr import (
    OcrField,
    OcrJob,
    OcrJobStatus,
    OcrResult,
)
from app.models.patients import Patient
from app.models.visits import Visit
from app.tests.ocr.test_ocr_auth_wiring import OcrAuthWiringTestCase


class TestKey246PreviousFields(OcrAuthWiringTestCase):
    """GET /visits/{visit_id}/ocr-fields/previous 계약 검증."""

    async def _make_patient(self, hospital_id: int, suffix: str) -> Patient:
        return await Patient.create(
            hospital_id=hospital_id,
            hospital_patient_no=f"SYN-246-{suffix}",
            name="합성 환자",
            birth_date=date(2000, 1, 1),
            phone="01000000000",
        )

    async def _make_visit(self, hospital_id: int, patient: Patient, visited_at: datetime) -> Visit:
        return await Visit.create(
            hospital_id=hospital_id,
            patient=patient,
            visited_at=visited_at,
        )

    async def _make_confirmed_field(
        self,
        visit: Visit,
        field_type: str,
        value: str,
        *,
        job_suffix: str = "",
        confirmed: bool = True,
        excluded_from_guide: bool = False,
    ) -> OcrField:
        job = await OcrJob.create(
            ocr_job_id=f"syn-246-{visit.visit_id}-{field_type}{job_suffix}",
            hospital_id=visit.hospital_id,
            visit=visit,
            requested_by=9999,
            status=OcrJobStatus.COMPLETED,
            progress=100,
            excluded_from_guide=excluded_from_guide,
        )
        result = await OcrResult.create(ocr_job=job, model_name="test-model")
        return await OcrField.create(
            ocr_result=result,
            field_type=field_type,
            extracted_value=value,
            is_confirmed=confirmed,
            confirmed_by=9999 if confirmed else None,
            confirmed_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC) if confirmed else None,
        )

    async def test_returns_previous_confirmed_field(self) -> None:
        """이전 방문의 확정 필드가 반환된다."""
        staff = await self.make_staff(login_id="k246a", roles=["staff"], hospital_name="알파의원")
        patient = await self._make_patient(staff.hospital_id, "a")

        prev_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 5, 20, 9, 0, tzinfo=UTC))
        await self._make_confirmed_field(prev_visit, "HEMOGLOBIN", "10.4")

        curr_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{curr_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["field_type"] == "HEMOGLOBIN"
        assert data[0]["value"] == "10.4"
        assert data[0]["visit_date"] == "2026-05-20"

    async def test_returns_empty_when_no_previous_visit(self) -> None:
        """이전 방문이 없으면 빈 배열을 반환한다."""
        staff = await self.make_staff(login_id="k246b", roles=["staff"], hospital_name="베타의원")
        patient = await self._make_patient(staff.hospital_id, "b")
        visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        assert response.json() == []

    async def test_excludes_unconfirmed_fields(self) -> None:
        """미확정 필드는 포함하지 않는다."""
        staff = await self.make_staff(login_id="k246c", roles=["staff"], hospital_name="감마의원")
        patient = await self._make_patient(staff.hospital_id, "c")

        prev_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 5, 20, 9, 0, tzinfo=UTC))
        await self._make_confirmed_field(prev_visit, "CA_125", "52", confirmed=False)

        curr_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{curr_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        assert response.json() == []

    async def test_excludes_other_hospital_fields(self) -> None:
        """타 병원 환자의 필드는 반환하지 않는다."""
        owner = await self.make_staff(login_id="k246d-owner", roles=["staff"], hospital_name="델타의원")
        outsider = await self.make_staff(login_id="k246d-out", roles=["staff"], hospital_name="에타의원")

        # 타 병원 환자·방문
        other_patient = await self._make_patient(outsider.hospital_id, "d-other")
        other_visit = await self._make_visit(
            outsider.hospital_id, other_patient, datetime(2026, 5, 20, 9, 0, tzinfo=UTC)
        )
        await self._make_confirmed_field(other_visit, "HEMOGLOBIN", "10.4", job_suffix="-o")

        # 내 병원 환자
        my_patient = await self._make_patient(owner.hospital_id, "d-mine")
        my_visit = await self._make_visit(owner.hospital_id, my_patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(owner.login_id)
        response = await self.get(f"/visits/{my_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        assert response.json() == []

    async def test_deduplicates_by_field_type_keeping_newest(self) -> None:
        """같은 field_type이 여러 방문에 있으면 가장 최근 방문 값을 반환한다."""
        staff = await self.make_staff(login_id="k246e", roles=["staff"], hospital_name="엡실론의원")
        patient = await self._make_patient(staff.hospital_id, "e")

        old_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 3, 10, 9, 0, tzinfo=UTC))
        await self._make_confirmed_field(old_visit, "HEMOGLOBIN", "9.8", job_suffix="-old")

        new_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 5, 20, 9, 0, tzinfo=UTC))
        await self._make_confirmed_field(new_visit, "HEMOGLOBIN", "10.4", job_suffix="-new")

        curr_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{curr_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["value"] == "10.4"  # 최신 방문 값

    async def test_future_visits_not_included(self) -> None:
        """현재 방문보다 미래 방문의 값은 포함하지 않는다."""
        staff = await self.make_staff(login_id="k246f", roles=["staff"], hospital_name="제타의원")
        patient = await self._make_patient(staff.hospital_id, "f")

        curr_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        future_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 9, 1, 9, 0, tzinfo=UTC))
        await self._make_confirmed_field(future_visit, "HEMOGLOBIN", "11.0", job_suffix="-future")

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{curr_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        assert response.json() == []

    async def test_visit_not_found_returns_404(self) -> None:
        """존재하지 않는 visit_id는 404를 반환한다."""
        staff = await self.make_staff(login_id="k246g", roles=["staff"], hospital_name="에타의원")
        token = await self.login(staff.login_id)
        response = await self.get("/visits/999999999/ocr-fields/previous", token)
        assert response.status_code == 404

    async def test_requires_authentication(self) -> None:
        """인증 없이 호출하면 401을 반환한다."""
        response = await self.get("/visits/1/ocr-fields/previous", token=None)
        assert response.status_code == 401

    async def test_excludes_fields_from_excluded_job(self) -> None:
        """excluded_from_guide=True job의 확정 필드는 반환하지 않는다."""
        staff = await self.make_staff(login_id="k246i", roles=["staff"], hospital_name="이오타의원")
        patient = await self._make_patient(staff.hospital_id, "i")

        prev_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 5, 20, 9, 0, tzinfo=UTC))
        await self._make_confirmed_field(prev_visit, "HEMOGLOBIN", "10.4", job_suffix="-excl", excluded_from_guide=True)

        curr_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{curr_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        assert response.json() == []

    async def test_multiple_field_types_all_returned(self) -> None:
        """여러 field_type이 각각 반환된다."""
        staff = await self.make_staff(login_id="k246h", roles=["staff"], hospital_name="에타의원")
        patient = await self._make_patient(staff.hospital_id, "h")

        prev_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 5, 20, 9, 0, tzinfo=UTC))
        job = await OcrJob.create(
            ocr_job_id="syn-246-h-multi",
            hospital_id=staff.hospital_id,
            visit=prev_visit,
            requested_by=9999,
            status=OcrJobStatus.COMPLETED,
            progress=100,
        )
        result = await OcrResult.create(ocr_job=job, model_name="test-model")
        for ft, val in [("HEMOGLOBIN", "10.4"), ("CA_125", "52"), ("AMH", "1.1")]:
            await OcrField.create(
                ocr_result=result,
                field_type=ft,
                extracted_value=val,
                is_confirmed=True,
                confirmed_by=9999,
                confirmed_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
            )

        curr_visit = await self._make_visit(staff.hospital_id, patient, datetime(2026, 8, 13, 9, 0, tzinfo=UTC))

        token = await self.login(staff.login_id)
        response = await self.get(f"/visits/{curr_visit.visit_id}/ocr-fields/previous", token)

        assert response.status_code == 200
        data = response.json()
        returned_types = {d["field_type"] for d in data}
        assert returned_types == {"HEMOGLOBIN", "CA_125", "AMH"}
