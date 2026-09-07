"""시드가 진료에 판독을 심는다 — KEY-271 P1.

규칙(`app/tests/fixtures/ocr_rows.py`)이 아니라 **심는 동작**을 잰다 — 작업
상태, 확정 도장, 재실행, 그리고 심은 것으로 실제 처방이 서는지.
"""

import csv
from datetime import UTC, datetime
from pathlib import Path

from tortoise.contrib.test import TestCase

from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository
from scripts.seed import _seed_ocr

CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-patients.csv"


def _rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def row_for(scenario: str) -> dict[str, str]:
    for row in _rows():
        if row["시나리오ID"] == scenario:
            return row
    raise AssertionError(f"CSV 에 {scenario} 가 없다 — 검사가 헛돈다")


class SeedPlantsReadingsTestCase(TestCase):
    async def make_world(self, chart: str) -> tuple[Hospital, Staff, Visit]:
        clinic = await Hospital.create(name=f"여성의원 {chart}")
        doctor = await Staff.create(
            hospital=clinic,
            login_id=f"seed_{chart}",
            password_hash="x",
            name="박연",
            roles=["doctor"],
            must_change_password=False,
        )
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no=chart,
            name="김서연",
            birth_date="1990-01-01",
            phone="01044521234",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id,
            visited_at=datetime(2026, 9, 3, 3, 0, tzinfo=UTC),
        )
        return clinic, doctor, visit

    async def test_a_visit_with_no_document_gets_no_job(self) -> None:
        """**판독 없는 진료를 남긴다.**

        판독 작업이 하나라도 있으면 `VisitService._refuse_if_locked` 가 담당의·
        진료일·진료과 변경을 409 `VISIT_LOCKED` 로 막는다 — **확정과 무관하다.**
        전부 심으면 시연에서 「진료 정보 고치기」를 보일 진료가 하나도 없다.
        """
        clinic, _, visit = await self.make_world("NO-DOC")

        planted = await _seed_ocr(visit, row_for("SYN-PCOS-06"), clinic.hospital_id)

        assert planted == (0, 0)
        assert not await OcrJob.filter(visit_id=visit.visit_id).exists()

    async def test_the_planted_job_is_completed_not_processing(self) -> None:
        """**기본값이 `PROCESSING` 이다.**

        그대로 두면 판독 결과 조회가 409 `OCR_RESULT_NOT_READY` 로 떨어져
        확인 화면이 아예 안 뜬다 — 심어 놓고 못 보는 상태가 된다.
        """
        clinic, _, visit = await self.make_world("DONE")

        await _seed_ocr(visit, row_for("SYN-PCOS-02"), clinic.hospital_id)

        job = await OcrJob.filter(visit_id=visit.visit_id).first()
        assert job is not None
        assert job.status == OcrJobStatus.COMPLETED, f"작업이 {job.status} 다 — 화면이 409 를 받는다"
        assert job.progress == 100
        assert job.excluded_from_guide is False, "제외된 작업은 finalize·generate 가 안 본다"

    async def test_a_staff_review_visit_is_left_unconfirmed(self) -> None:
        """**전부 확정으로 심으면 확인 화면이 죽는다.**

        「확인할 항목 0개」가 뜨고, 다시 확정하면 409 `OCR_FIELD_CONFIRMED` 다.
        S1-6·S1-7 을 볼 표본이 이 두 진료다.
        """
        clinic, _, visit = await self.make_world("REVIEW")

        await _seed_ocr(visit, row_for("SYN-PCOS-08"), clinic.hospital_id)

        fields = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id)
        assert fields, "필드를 하나도 안 심었다"
        assert all(not field.is_confirmed for field in fields), "확인 화면에 볼 것이 없다"
        result = await OcrResult.filter(ocr_job__visit_id=visit.visit_id).first()
        assert result is not None and result.confirmed_by is None

    async def test_a_confirmed_visit_carries_the_stamp_of_a_person(self) -> None:
        """**사람 없이 사람이 한 일을 만들지 않는다.**

        확정은 담당의가 찍은 것으로 남긴다 — `seed_smoke_fixture` 가 승인자
        없이는 승인 상태를 안 만드는 것과 같은 까닭이다.
        """
        clinic, doctor, visit = await self.make_world("STAMP")

        await _seed_ocr(visit, row_for("SYN-PCOS-02"), clinic.hospital_id)

        fields = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id)
        assert all(field.is_confirmed for field in fields)
        assert all(field.confirmed_by == doctor.staff_id for field in fields)
        assert all(field.confirmed_at is not None for field in fields)

    async def test_a_confirmed_visit_actually_builds_a_prescription(self) -> None:
        """**도장만 찍고 필드가 모자란 상태**를 잡는다.

        「확정으로 심었다」가 참이어도 `PRESCRIPTION_SET` 이나 `FREQUENCY` 가
        빠지면 「확인 완료」가 422 로 멈춘다. 심은 것으로 사슬이 끝까지 도는지를
        여기서 잰다.
        """
        clinic, doctor, visit = await self.make_world("BUILD")
        await _seed_ocr(visit, row_for("SYN-PCOS-02"), clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        items = await prescription.items.all()
        assert [item.name for item in items] == ["야즈정(드로스피레논/에티닐에스트라디올)"]
        assert prescription.prescription_set == "PCOS · 야즈 (처음)"

    async def test_a_pack_count_becomes_days(self) -> None:
        """**「3통이면 84일. 일수로 읽으면 3일」** — `SYN-PCOS-02` 의 케이스의도 그대로다.

        판독은 원문 `3` 을 읽고 `unit` 에 「통」을 남긴다. 일수로 바꾸는 것은
        읽는 쪽 몫이다 — 안 하면 소진 문자가 81일 일찍 예약된다.
        """
        clinic, doctor, visit = await self.make_world("PACK")
        row = row_for("SYN-PCOS-02")
        assert (row["총투원문"], row["총투단위"], row["처방일수"]) == ("1/1/3", "통수", "84")
        await _seed_ocr(visit, row, clinic.hospital_id)

        stored = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id, field_type="DURATION_DAYS").first()
        assert stored is not None
        assert (stored.extracted_value, stored.unit) == ("3", "통"), "환산한 값을 심으면 판독이 읽은 것이 아니다"

        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))
        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)
        item = (await prescription.items.all())[0]
        assert item.duration_days == 84, f"{item.duration_days}일로 섰다 — 3통을 3일로 읽었다"

    async def test_a_day_count_is_not_multiplied(self) -> None:
        """같은 세트라도 일수 처방은 그대로다 — 단위는 세트가 아니라 그 줄의 성질이다."""
        clinic, doctor, visit = await self.make_world("DAYS")
        row = next(
            r for r in _rows() if r["총투단위"] == "일수" and r["처방일수"] == "84" and r["진료상태"] == "발송 완료"
        )
        await _seed_ocr(visit, row, clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        assert (await prescription.items.all())[0].duration_days == 84

    async def test_the_second_drug_lands_too(self) -> None:
        """약이 둘인 행이 13건 있다 — 번호 접미사가 실제로 도는지 잰다."""
        clinic, doctor, visit = await self.make_world("TWO")
        two = next(r for r in _rows() if " + " in r["약"] and r["진료상태"] not in ("진료기록 없음", ""))
        await _seed_ocr(visit, two, clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        names = [item.name for item in await prescription.items.all()]
        assert len(names) == 2, f"약이 {len(names)}개다 — {names}"

    async def test_seeding_twice_does_not_stack(self) -> None:
        """**같은 명령을 반복해도 쌓이지 않는다** — 시드 전체가 그 규칙으로 짜여 있다."""
        clinic, _, visit = await self.make_world("AGAIN")
        first = await _seed_ocr(visit, row_for("SYN-PCOS-02"), clinic.hospital_id)

        second = await _seed_ocr(visit, row_for("SYN-PCOS-02"), clinic.hospital_id)

        assert second == (0, 0), "두 번째 실행이 또 심었다"
        assert await OcrJob.filter(visit_id=visit.visit_id).count() == 1
        assert await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id).count() == first[1]

    async def test_a_visit_without_a_doctor_is_refused(self) -> None:
        """**담당의가 없으면 아예 안 심는다.**

        `requested_by` 는 「누가 읽어 달라고 했는가」다. 적을 사람이 없는데 `0`
        같은 값을 넣으면 아무도 아닌 사람이 판독을 요청한 것이 된다.
        """
        clinic = await Hospital.create(name="담당의 없는 의원")
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no="NO-DOC-2",
            name="이지우",
            birth_date="1995-04-02",
            phone="01011112222",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 9, 3, 3, 0, tzinfo=UTC),
        )

        planted = await _seed_ocr(visit, row_for("SYN-PCOS-02"), clinic.hospital_id)

        assert planted == (0, 0)
        assert not await OcrJob.filter(visit_id=visit.visit_id).exists()
