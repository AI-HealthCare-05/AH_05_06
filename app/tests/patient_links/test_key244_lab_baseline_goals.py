"""환자 D1 목표가 병원 검사 기준선과 확정 OCR만 사용하는가 — KEY-244."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models.catalog import BaselineDirection, LabBaseline, PrescriptionSet, SetDisease
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.prescriptions import Prescription
from app.models.visits import GuideDocument, GuideStatus, Visit
from app.tests.patient_links.test_patient_links import (
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

CONFIRMED_AT = datetime(2026, 9, 2, 9, tzinfo=ZoneInfo("Asia/Seoul"))


async def _ocr_result(guide: GuideDocument, suffix: str = "current") -> OcrResult:
    visit = await Visit.get(visit_id=guide.visit_id)
    job = await OcrJob.create(
        ocr_job_id=f"synthetic-key244-{suffix}",
        hospital_id=visit.hospital_id,
        visit=visit,
        status=OcrJobStatus.COMPLETED,
        progress=100,
        requested_by=1,
        started_at=CONFIRMED_AT,
    )
    return await OcrResult.create(
        ocr_job=job,
        model_name="synthetic-key244-model",
    )


async def _field(
    result: OcrResult,
    field_type: str,
    value: str,
    *,
    confirmed: bool = True,
    confirmed_at: datetime | None = CONFIRMED_AT,
) -> OcrField:
    return await OcrField.create(
        ocr_result=result,
        field_type=field_type,
        extracted_value=value,
        is_confirmed=confirmed,
        confirmed_by=1 if confirmed else None,
        confirmed_at=confirmed_at,
    )


async def _baseline(
    guide: GuideDocument,
    *,
    doctor_id: int | None,
    name: str,
    keywords: str,
    low: str | None = None,
    high: str | None = None,
    direction: BaselineDirection = BaselineDirection.KEEP,
    unit: str = "",
    position: int = 0,
    disease: SetDisease = SetDisease.ENDOMETRIOSIS,
) -> LabBaseline:
    return await LabBaseline.create(
        hospital_id=guide.hospital_id,
        doctor_id=doctor_id,
        disease=disease,
        name=name,
        direction=direction,
        low=Decimal(low) if low is not None else None,
        high=Decimal(high) if high is not None else None,
        keywords=keywords,
        unit=unit,
        position=position,
    )


class TestKey244LabBaselineGoals(PatientLinkTestCase):
    async def test_doctor_baselines_and_latest_confirmed_values_build_goals(self) -> None:
        hospital = await make_hospital("KEY-244 기준선 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        doctor = await make_staff(hospital, "key244-doctor", ["doctor"])
        visit = await Visit.get(visit_id=guide.visit_id)
        visit.doctor_id = doctor.staff_id
        await visit.save(update_fields=["doctor_id"])

        # 의원 공통 값보다 담당 의사의 판을 우선한다.
        await _baseline(guide, doctor_id=None, name="혈색소 Hb", keywords="Hb", low="11", unit="g/dL")
        await _baseline(
            guide,
            doctor_id=doctor.staff_id,
            name="혈색소 Hb",
            keywords="Hb, Hemoglobin",
            low="12",
            unit="g/dL",
        )
        await _baseline(
            guide,
            doctor_id=doctor.staff_id,
            name="CA-125",
            keywords="CA-125, CA125",
            high="35",
            direction=BaselineDirection.LOWER,
            unit="U/L",
            position=1,
        )
        await _baseline(
            guide,
            doctor_id=doctor.staff_id,
            name="AMH",
            keywords="AMH",
            low="1",
            unit="ng/mL",
            position=2,
        )

        older = await _ocr_result(guide, "older")
        await _field(older, "HB", "8.1", confirmed_at=datetime(2026, 8, 1, tzinfo=ZoneInfo("Asia/Seoul")))
        current = await _ocr_result(guide)
        await _field(current, "DIAGNOSIS", "자궁내막증")
        # 별칭 선언 순서(Hb가 먼저)가 아니라 모든 별칭 중 최신값을 고른다.
        await _field(current, "HEMOGLOBIN", "2차 10.4 g/dL")
        await _field(current, "CA_125", "41")
        await _field(current, "AMH", "2.2", confirmed=False, confirmed_at=None)

        issued = await self.issue(guide, doctor)
        async with self.client() as client:
            response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        assert response.json()["guide"]["goals"] == [
            {
                "n": "혈색소 Hb",
                "now": "10.4",
                "t": "12",
                "hasChart": True,
                "rangeLabel": "기준 12 g/dL 이상",
            },
            {
                "n": "CA-125",
                "now": "41",
                "t": "35",
                "hasChart": True,
                "rangeLabel": "기준 35 U/L 미만",
            },
        ]

    async def test_empty_baseline_keeps_confirmed_value_without_target_calculation(self) -> None:
        hospital = await make_hospital("KEY-244 빈기준선 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key244-staff", ["staff"])
        doctor = await make_staff(hospital, "key244-common-fallback-doctor", ["doctor"])
        visit = await Visit.get(visit_id=guide.visit_id)
        visit.doctor_id = doctor.staff_id
        await visit.save(update_fields=["doctor_id"])
        await _baseline(guide, doctor_id=None, name="AMH", keywords="AMH", position=0)
        await _baseline(guide, doctor_id=None, name="혈색소 Hb", keywords="Hb", low="12", position=1)

        result = await _ocr_result(guide)
        await _field(result, "DIAGNOSIS", "ENDOMETRIOSIS")
        await _field(result, "AMH", "1.7")
        # is_confirmed만 켜지고 확정 시각이 없는 불완전 상태도 계산 입력이 아니다.
        await _field(result, "HB", "9.8", confirmed=True, confirmed_at=None)

        issued = await self.issue(guide, staff)
        async with self.client() as client:
            response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        assert response.json()["guide"]["goals"] == [
            {
                "n": "AMH",
                "now": "1.7",
                "hasChart": False,
            }
        ]

    async def test_confirmed_lab_without_confirmed_diagnosis_does_not_guess_a_baseline_group(self) -> None:
        hospital = await make_hospital("KEY-244 진단미확정 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key244-no-diagnosis", ["doctor"])
        await _baseline(guide, doctor_id=None, name="혈색소 Hb", keywords="Hb", low="12")

        result = await _ocr_result(guide)
        await _field(result, "DIAGNOSIS", "자궁내막증", confirmed=False, confirmed_at=None)
        await _field(result, "HB", "10.4")

        issued = await self.issue(guide, staff)
        async with self.client() as client:
            response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        assert response.json()["guide"]["goals"] == []

    async def test_coexisting_diagnoses_include_both_baseline_groups(self) -> None:
        hospital = await make_hospital("KEY-244 병존진단 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key244-coexisting", ["doctor"])
        await _baseline(
            guide,
            doctor_id=None,
            name="AMH",
            keywords="AMH",
            low="1",
            disease=SetDisease.PCOS,
        )
        await _baseline(guide, doctor_id=None, name="CA-125", keywords="CA125", high="35")

        result = await _ocr_result(guide)
        await _field(result, "DIAGNOSIS", "다낭성난소증후군 동반 자궁내막증")
        await _field(result, "AMH", "0.8")
        await _field(result, "CA125", "41")

        issued = await self.issue(guide, staff)
        async with self.client() as client:
            response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        assert [goal["n"] for goal in response.json()["guide"]["goals"]] == ["AMH", "CA-125"]

    async def test_structured_prescription_set_classifies_confirmed_icd_diagnosis(self) -> None:
        hospital = await make_hospital("KEY-244 구조화질환 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key244-structured", ["doctor"])
        catalog = await PrescriptionSet.create(name="PCOS 구조화 세트", disease=SetDisease.PCOS)
        await Prescription.create(visit_id=guide.visit_id, prescription_set=catalog.name)
        await _baseline(
            guide,
            doctor_id=None,
            name="AMH",
            keywords="AMH",
            low="1",
            disease=SetDisease.PCOS,
        )

        result = await _ocr_result(guide)
        await _field(result, "DIAGNOSIS", "E28.2")
        await _field(result, "AMH", "0.8")

        issued = await self.issue(guide, staff)
        async with self.client() as client:
            response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        assert response.json()["guide"]["goals"][0]["n"] == "AMH"

    async def test_unmatched_baseline_is_observable_without_exposing_a_goal(self) -> None:
        hospital = await make_hospital("KEY-244 미매칭관측 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key244-unmatched", ["doctor"])
        await _baseline(guide, doctor_id=None, name="CA-125", keywords="CA125", high="35")
        result = await _ocr_result(guide)
        await _field(result, "DIAGNOSIS", "자궁내막증")

        issued = await self.issue(guide, staff)
        with self.assertLogs("app.patient_links", level="WARNING") as captured:
            async with self.client() as client:
                response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        assert response.json()["guide"]["goals"] == []
        assert "baseline did not match" in captured.output[0]
