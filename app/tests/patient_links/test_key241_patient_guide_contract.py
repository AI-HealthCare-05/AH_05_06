"""환자 P2~P5가 v3.0.0 계약의 실제 승인·처방 데이터로 채워지는가 — KEY-241."""

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.visits import GuideDocument, GuideSection, GuideSectionKey, GuideStatus, Visit
from app.services.patient_links import calculate_medication_progress
from app.tests.patient_links.test_patient_links import (
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

FIXED_NOW = datetime(2026, 8, 24, 12, tzinfo=ZoneInfo("Asia/Seoul"))
OCR_STARTED_AT = datetime(2026, 8, 13, 9, tzinfo=ZoneInfo("Asia/Seoul"))
OLDER_OCR_STARTED_AT = datetime(2026, 8, 1, 9, tzinfo=ZoneInfo("Asia/Seoul"))
OLDER_CONFIRMED_AT = datetime(2026, 8, 20, 12, tzinfo=ZoneInfo("Asia/Seoul"))


@pytest.mark.parametrize(
    ("as_of", "day_on", "remaining", "pct"),
    [
        (date(2025, 12, 31), 0, 84, 0),
        (date(2026, 1, 1), 1, 83, 1),
        (date(2026, 2, 11), 42, 42, 50),
        (date(2026, 3, 25), 84, 0, 100),
        (date(2026, 5, 1), 121, 0, 100),
    ],
)
def test_medication_progress_is_rounded_and_clamped(
    as_of: date,
    day_on: int,
    remaining: int,
    pct: int,
) -> None:
    progress = calculate_medication_progress(
        started_at=datetime(2026, 1, 1, 9, tzinfo=ZoneInfo("Asia/Seoul")),
        prescribed_days=84,
        as_of=as_of,
    )

    assert progress.day_on == day_on
    assert progress.remaining == remaining
    assert progress.pct == pct
    assert 0 <= progress.pct <= 100


def test_non_positive_prescription_days_are_not_a_progress_contract() -> None:
    with pytest.raises(ValueError, match="prescribed_days must be positive"):
        calculate_medication_progress(
            started_at=FIXED_NOW,
            prescribed_days=0,
            as_of=FIXED_NOW.date(),
        )


async def _add_public_sources(
    guide: GuideDocument,
    *,
    started_at: datetime | None = OCR_STARTED_AT,
    duration_days: int | None = 84,
    include_diagnosis: bool = True,
) -> None:
    visit = await Visit.get(visit_id=guide.visit_id)
    # 화면의 진료일과 복약 진행률 기준일이 서로 다른 소스라는 점을 고정한다.
    visit.visited_at = datetime(2026, 8, 10, 9, tzinfo=ZoneInfo("Asia/Seoul"))
    await visit.save(update_fields=["visited_at"])

    older_ocr_job = await OcrJob.create(
        ocr_job_id="synthetic-key241-older-ocr-job",
        hospital_id=visit.hospital_id,
        visit=visit,
        status=OcrJobStatus.COMPLETED,
        progress=100,
        requested_by=1,
        started_at=OLDER_OCR_STARTED_AT,
    )
    older_result = await OcrResult.create(
        ocr_job=older_ocr_job,
        model_name="synthetic-key241-older-model",
    )
    await OcrField.create(
        ocr_result=older_result,
        field_type="MEDICATION_NAME",
        extracted_value="환자에게 내보내면 안 되는 이전 확정 필드",
        is_confirmed=True,
        confirmed_by=1,
        confirmed_at=OLDER_CONFIRMED_AT,
    )

    ocr_job = await OcrJob.create(
        ocr_job_id="synthetic-key241-ocr-job",
        hospital_id=visit.hospital_id,
        visit=visit,
        status=OcrJobStatus.COMPLETED,
        progress=100,
        requested_by=1,
        started_at=started_at,
    )
    ocr_result = await OcrResult.create(
        ocr_job=ocr_job,
        model_name="synthetic-key241-model",
    )
    await OcrField.create(
        ocr_result=ocr_result,
        field_type="MEDICATION_NAME",
        extracted_value="환자에게 내보내면 안 되는 최신 확정 필드",
        is_confirmed=True,
        confirmed_by=1,
        confirmed_at=FIXED_NOW,
    )
    if include_diagnosis:
        await OcrField.create(
            ocr_result=ocr_result,
            field_type="DIAGNOSIS",
            extracted_value="환자에게 내보내면 안 되는 생성 진단",
            corrected_value="자궁내막증",
            is_confirmed=True,
            confirmed_by=1,
            confirmed_at=FIXED_NOW,
        )

    prescription = await Prescription.create(
        visit=visit,
        prescription_set="자궁내막증 · 비잔 (계속)",
    )
    await PrescriptionItem.create(
        prescription=prescription,
        name="비잔정(디에노게스트) 2mg",
        frequency="1일 1회",
        duration_days=duration_days,
    )
    await PrescriptionItem.create(
        prescription=prescription,
        name="진통제",
        frequency="필요시",
    )

    for key, body in (
        (GuideSectionKey.CAUTION, "합성 승인 주의 안내"),
        (GuideSectionKey.EMERGENCY, "합성 승인 응급 안내"),
        (GuideSectionKey.LIFE, "합성 승인 생활관리 안내"),
        (GuideSectionKey.MESSAGES, "합성 승인 병원 안내"),
    ):
        await GuideSection.create(
            guide_document=guide,
            section_key=key,
            generated_body=f"환자에게 내보내면 안 되는 {key.value} 생성 원문",
            edited_body=body,
        )


class TestKey241PatientGuideContract(PatientLinkTestCase):
    async def test_v3_contract_uses_available_models_and_keeps_approved_sections(self) -> None:
        hospital = await make_hospital("KEY-241 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key241-staff", ["staff"])
        await _add_public_sources(guide)

        with patch("app.services.patient_links.now", return_value=FIXED_NOW):
            issued = await self.issue(guide, staff)
            async with self.client() as client:
                response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["visit"] == "2026.08.10"
        assert body["clinic"] == "KEY-241 합성여성의원"
        assert body["disease"] == "자궁내막증 · 비잔정 복용 중"
        assert body["stat"] == {
            "drugName": "비잔정 2mg",
            "drugSub": "성분 · 디에노게스트 · 1일 1회 · 84일분",
            "prescribed": 84,
            "dayOn": 12,
            "remaining": 72,
            "pct": 14,
            "out": "ⓘ 11월 5일경 약이 소진돼요",
            "why": "합성 승인 복약 안내",
        }
        assert body["guide"] == {
            "summary": "합성 승인 복약 안내",
            "goals": [],
            "drug": {
                "n": "비잔정 2mg",
                "s": "성분 · 디에노게스트",
                "d": "1일 1회 · 84일분",
            },
            "why": ["합성 승인 복약 안내"],
            "how": "1일 1회 · 84일분",
        }
        assert body["care"] == {
            "blocks": [{"t": "주의사항", "p": ["합성 승인 주의 안내"]}],
            "danger": ["합성 승인 응급 안내"],
        }
        assert body["life"] == {
            "sub": "자궁내막증 · 비잔정 복용 중",
            "challenges": [],
            "axes": {"생활관리": {"title": "생활관리", "p": ["합성 승인 생활관리 안내"]}},
        }
        assert "chat" not in body, "질문 칩 저장 소스가 없는데 목업 문구를 지어내면 안 된다"
        assert body["sections"] == [
            {"key": "medication", "body": "합성 승인 복약 안내"},
            {"key": "caution", "body": "합성 승인 주의 안내"},
            {"key": "emergency", "body": "합성 승인 응급 안내"},
            {"key": "life", "body": "합성 승인 생활관리 안내"},
            {"key": "messages", "body": "합성 승인 병원 안내"},
        ]

        serialized = response.text
        for forbidden in (
            "환자에게 내보내면 안 되는",
            "ocr_job_id",
            "ocr_result_id",
            "approved_by",
            "phone",
            "hospital_patient_no",
        ):
            assert forbidden not in serialized

    async def test_missing_structured_sources_are_omitted_instead_of_mocked(self) -> None:
        hospital = await make_hospital("KEY-241 소스없음 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key241-empty", ["doctor"])

        issued = await self.issue(guide, staff)
        async with self.client() as client:
            response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert "stat" not in body
        assert "disease" not in body
        assert "care" not in body
        assert "life" not in body
        assert "chat" not in body
        assert body["guide"]["goals"] == []
        assert body["guide"]["summary"] == "합성 승인 복약 안내"
        assert body["sections"] == [{"key": "medication", "body": "합성 승인 복약 안내"}]

    async def test_null_ocr_started_at_keeps_stat_but_omits_progress_fields(self) -> None:
        hospital = await make_hospital("KEY-241 시작일없음 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key241-null-start", ["staff"])
        await _add_public_sources(guide, started_at=None)

        with patch("app.services.patient_links.now", return_value=FIXED_NOW):
            issued = await self.issue(guide, staff)
            async with self.client() as client:
                response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        stat = response.json()["stat"]
        assert stat == {
            "drugName": "비잔정 2mg",
            "drugSub": "성분 · 디에노게스트 · 1일 1회 · 84일분",
            "prescribed": 84,
            "why": "합성 승인 복약 안내",
        }
        assert {"dayOn", "remaining", "pct", "out"}.isdisjoint(stat)

    async def test_zero_prescribed_days_returns_200_and_omits_progress_fields(self) -> None:
        hospital = await make_hospital("KEY-241 처방일수0 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key241-zero-days", ["doctor"])
        await _add_public_sources(guide, duration_days=0)

        with patch("app.services.patient_links.now", return_value=FIXED_NOW):
            issued = await self.issue(guide, staff)
            async with self.client() as client:
                response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        stat = response.json()["stat"]
        assert stat == {
            "drugName": "비잔정 2mg",
            "drugSub": "성분 · 디에노게스트 · 1일 1회",
            "prescribed": 0,
            "why": "합성 승인 복약 안내",
        }
        assert {"dayOn", "remaining", "pct", "out"}.isdisjoint(stat)

    async def test_prescription_set_is_not_exposed_as_a_confirmed_disease(self) -> None:
        hospital = await make_hospital("KEY-241 진단없음 합성여성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key241-no-diagnosis", ["staff"])
        await _add_public_sources(guide, include_diagnosis=False)

        with patch("app.services.patient_links.now", return_value=FIXED_NOW):
            issued = await self.issue(guide, staff)
            async with self.client() as client:
                response = await client.get(issued.json()["path"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert "disease" not in body
        assert "자궁내막증 · 비잔 (계속)" not in response.text
        assert body["stat"]["drugName"] == "비잔정 2mg"
