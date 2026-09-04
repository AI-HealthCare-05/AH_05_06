"""확정된 OCR 필드 → Prescription·PrescriptionItem 구조화 저장 — KEY-66."""

from datetime import UTC, datetime

import pytest
from tortoise.contrib.test import TestCase

from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.prescriptions import AS_NEEDED, Prescription
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository


class FinalizeOcrTestCase(TestCase):
    async def make_world(self, chart: str) -> tuple[OcrActor, Visit, OcrResult]:
        clinic = await Hospital.create(name=f"여성의원 {chart}")
        staff = await Staff.create(
            hospital=clinic,
            login_id=f"fo_{chart}",
            password_hash="x",
            name="이지은",
            roles=["staff"],
            must_change_password=False,
        )
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no=chart,
            name="박지현",
            birth_date="1992-05-10",
            phone="01011112222",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
        )
        job = await OcrJob.create(
            ocr_job_id=f"fo-{chart}",
            hospital_id=clinic.hospital_id,
            visit=visit,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
        )
        result = await OcrResult.create(ocr_job=job, model_name="test")
        actor = OcrActor(
            staff_id=staff.staff_id,
            hospital_id=staff.hospital_id,
            roles=frozenset(staff.roles or []),
        )
        return actor, visit, result

    async def _add_confirmed_field(
        self,
        result: OcrResult,
        field_type: str,
        value: str,
        actor: OcrActor,
    ) -> OcrField:
        return await OcrField.create(
            ocr_result=result,
            field_type=field_type,
            extracted_value=value,
            is_confirmed=True,
            confirmed_by=actor.staff_id,
            confirmed_at=datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        )

    async def test_prescription_created_from_confirmed_fields(self) -> None:
        """정상 케이스 — PRESCRIPTION_SET·MEDICATION_NAME·DURATION_DAYS 확정 후 Prescription 생성."""
        actor, visit, result = await self.make_world("FO-01")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)

        repo = TortoiseOcrRepository()
        prescription = await repo.finalize_ocr(visit.visit_id, actor)

        assert prescription.prescription_set == "자궁내막증 · 비잔 (처음)"
        items = list(prescription.items)
        assert len(items) == 1
        assert items[0].name == "비잔정 2mg"
        assert items[0].frequency == "1일 1회"
        assert items[0].duration_days == 84

    async def test_refinalizing_updates_existing_prescription(self) -> None:
        """재확정 — 이미 Prescription이 있으면 값을 덮어쓰고 항목을 재생성한다."""
        actor, visit, result = await self.make_world("FO-02")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)

        repo = TortoiseOcrRepository()
        first = await repo.finalize_ocr(visit.visit_id, actor)
        first_id = first.prescription_id

        # 처방 세트를 재확정으로 바꾼다
        await OcrField.filter(ocr_result=result, field_type="PRESCRIPTION_SET").update(
            extracted_value="자궁내막증 · 비잔 (계속)"
        )

        second = await repo.finalize_ocr(visit.visit_id, actor)

        assert second.prescription_id == first_id, "재확정은 새 행을 만들면 안 된다"
        assert second.prescription_set == "자궁내막증 · 비잔 (계속)"
        assert await Prescription.filter(visit_id=visit.visit_id).count() == 1

    async def test_multiple_drugs_create_multiple_items(self) -> None:
        """복수 약품 — MEDICATION_NAME_2까지 있으면 PrescriptionItem이 두 개 생긴다."""
        actor, visit, result = await self.make_world("FO-03")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME_2", "이부프로펜 400mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)

        repo = TortoiseOcrRepository()
        prescription = await repo.finalize_ocr(visit.visit_id, actor)

        items = sorted(prescription.items, key=lambda i: i.prescription_item_id)
        assert len(items) == 2
        assert items[0].name == "비잔정 2mg"
        assert items[0].duration_days == 84
        assert items[1].name == "이부프로펜 400mg"
        assert items[1].duration_days is None, "DURATION_DAYS_2 없으면 None"

    async def test_item_without_duration_has_null_duration_days(self) -> None:
        """처방일수 없음 — DURATION_DAYS 필드가 없으면 duration_days가 None이다."""
        actor, visit, result = await self.make_world("FO-04")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "PCOS · 야즈 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "야즈정", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)

        repo = TortoiseOcrRepository()
        prescription = await repo.finalize_ocr(visit.visit_id, actor)

        items = list(prescription.items)
        assert len(items) == 1
        assert items[0].duration_days is None

    async def test_refinalizing_replaces_old_items(self) -> None:
        """재확정 시 기존 항목이 삭제되고 새 항목으로 교체된다."""
        actor, visit, result = await self.make_world("FO-05")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)

        repo = TortoiseOcrRepository()
        first = await repo.finalize_ocr(visit.visit_id, actor)
        old_item_ids = {item.prescription_item_id for item in first.items}

        # 약품을 MEDICATION_NAME_2 추가
        await self._add_confirmed_field(result, "MEDICATION_NAME_2", "진통제", actor)

        second = await repo.finalize_ocr(visit.visit_id, actor)
        new_item_ids = {item.prescription_item_id for item in second.items}

        assert len(second.items) == 2
        assert not old_item_ids & new_item_ids, "기존 항목 ID가 재사용되면 안 된다"

    async def test_unconfirmed_field_blocks_finalize(self) -> None:
        """미확정 필드가 있으면 409를 돌려준다."""
        actor, visit, result = await self.make_world("FO-06")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "PCOS · 야즈 (처음)", actor)
        await OcrField.create(
            ocr_result=result,
            field_type="MEDICATION_NAME",
            extracted_value="야즈정",
            is_confirmed=False,
        )

        with pytest.raises(OcrApiError) as exc:
            await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        assert exc.value.code == "OCR_NOT_CONFIRMED"

    async def test_missing_prescription_set_blocks_finalize(self) -> None:
        """PRESCRIPTION_SET 필드가 없으면 422를 돌려준다."""
        actor, visit, result = await self.make_world("FO-07")
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)

        with pytest.raises(OcrApiError) as exc:
            await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        assert exc.value.code == "MISSING_PRESCRIPTION_SET"

    async def test_missing_frequency_blocks_finalize(self) -> None:
        """FREQUENCY 필드가 없으면 422를 돌려준다."""
        actor, visit, result = await self.make_world("FO-13")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)

        with pytest.raises(OcrApiError) as exc:
            await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        assert exc.value.code == "MISSING_FREQUENCY"

    async def test_prescription_is_hospital_scoped(self) -> None:
        """다른 병원의 visit_id를 넘기면 404가 나온다."""
        actor, visit, _ = await self.make_world("FO-08")

        other_clinic = await Hospital.create(name="타병원")
        other_staff = await Staff.create(
            hospital=other_clinic,
            login_id="fo_other",
            password_hash="x",
            name="김철수",
            roles=["staff"],
            must_change_password=False,
        )
        other_actor = OcrActor(
            staff_id=other_staff.staff_id,
            hospital_id=other_clinic.hospital_id,
            roles=frozenset(other_staff.roles or []),
        )

        with pytest.raises(OcrApiError) as exc:
            await TortoiseOcrRepository().finalize_ocr(visit.visit_id, other_actor)

        assert exc.value.status_code == 404

    async def test_excluded_job_does_not_create_prescription(self) -> None:
        """excluded_from_guide=True인 job으로는 finalize_ocr이 404를 반환한다."""
        actor, visit, result = await self.make_world("FO-09")
        job = await OcrJob.filter(visit_id=visit.visit_id).first()
        assert job is not None
        job.excluded_from_guide = True
        await job.save(update_fields=("excluded_from_guide",))

        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)

        with pytest.raises(OcrApiError) as exc:
            await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        assert exc.value.status_code == 404

    async def test_mixed_frequency_as_needed_drug_has_no_duration(self) -> None:
        """비잔정(1일 1회, 84일) + 진통제(필요시) — 필요시 약은 duration_days=None."""
        actor, visit, result = await self.make_world("FO-10")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME_2", "이부프로펜 400mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY_2", AS_NEEDED, actor)

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        items = sorted(prescription.items, key=lambda i: i.prescription_item_id)
        assert len(items) == 2
        assert items[0].frequency == "1일 1회"
        assert items[0].duration_days == 84
        assert items[1].frequency == AS_NEEDED
        assert items[1].duration_days is None, "필요시 약에 기간을 붙이면 안 된다"

    async def test_suffix_gap_does_not_drop_later_drugs(self) -> None:
        """MEDICATION_NAME_2 없이 _3만 있어도 _3 약이 누락되지 않는다."""
        actor, visit, result = await self.make_world("FO-11")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84", actor)
        # _2 없이 _3만 있는 gap 상황
        await self._add_confirmed_field(result, "MEDICATION_NAME_3", "엽산정", actor)
        await self._add_confirmed_field(result, "FREQUENCY_3", "1일 1회", actor)

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        names = {item.name for item in prescription.items}
        assert "엽산정" in names, "suffix gap이 있어도 _3 약이 포함되어야 한다"

    async def test_duration_days_with_korean_suffix_is_parsed(self) -> None:
        """DURATION_DAYS 값이 '84일'처럼 한글이 섞여도 84로 파싱된다."""
        actor, visit, result = await self.make_world("FO-12")
        await self._add_confirmed_field(result, "PRESCRIPTION_SET", "자궁내막증 · 비잔 (처음)", actor)
        await self._add_confirmed_field(result, "MEDICATION_NAME", "비잔정 2mg", actor)
        await self._add_confirmed_field(result, "FREQUENCY", "1일 1회", actor)
        await self._add_confirmed_field(result, "DURATION_DAYS", "84일", actor)

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        items = list(prescription.items)
        assert items[0].duration_days == 84
