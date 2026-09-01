"""판독이 못 읽은 값을 적어 넣는다 — KEY-234, 와이어프레임 S1-7 「직접 입력」.

**고치기(PATCH)와 다른 길이다.** 저쪽은 있는 줄의 값을 바꾸고, 이쪽은 **줄
자체가 없는** 것을 만든다. 판독이 못 찾은 항목은 레코드로 남지 않아서, 화면이
값을 적어도 보낼 곳이 없었다 — 「저장 안 됨」이라 적어 두고 새로고침하면 사라졌다.
"""

from datetime import UTC, datetime

from tortoise.contrib.test import TestCase

from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository


class WriteFieldTestCase(TestCase):
    async def make_world(self, chart: str, *, with_result: bool = True) -> tuple[OcrActor, Visit]:
        clinic = await Hospital.create(name=f"여성의원 {chart}")
        staff = await Staff.create(
            hospital=clinic,
            login_id=f"wf_{chart}",
            password_hash="x",
            name="한소영",
            roles=["staff"],
            must_change_password=False,
        )
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no=chart,
            name="김서연",
            birth_date="1990-01-01",
            phone="01000000000",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        )
        if with_result:
            job = await OcrJob.create(
                ocr_job_id=f"wf-{chart}",
                hospital_id=clinic.hospital_id,
                visit=visit,
                requested_by=staff.staff_id,
                status=OcrJobStatus.COMPLETED,
            )
            await OcrResult.create(ocr_job=job, model_name="test")
        # **진짜 `OcrActor` 를 만든다.** 대역을 손으로 만들면 진짜에 있는 칸
        # (`roles`)이 빠져도 검사는 통과한다 — 그 칸을 보게 되는 날 본 코드가
        # 아니라 검사만 먼저 깨진다.
        return OcrActor(
            staff_id=staff.staff_id,
            hospital_id=staff.hospital_id,
            roles=frozenset(staff.roles or []),
        ), visit

    async def test_a_missing_row_is_created(self) -> None:
        """**줄이 없던 항목이 생긴다.** 이것이 없어서 「저장 안 됨」이었다."""
        actor, visit = await self.make_world("WF-01")
        assert not await OcrField.filter(field_type="TSH").exists()

        field, _ = await TortoiseOcrRepository().write_field(visit.visit_id, "TSH", "2.1", actor)

        assert field is not None
        assert field.field_type == "TSH"
        assert field.corrected_value == "2.1"
        assert field.modified_by == actor.staff_id, "누가 적었는지 안 남았다"

    async def test_writing_twice_updates_the_same_row(self) -> None:
        """다시 적으면 같은 줄을 고친다 — 줄이 둘이 되면 어느 것이 값인지 모른다."""
        actor, visit = await self.make_world("WF-02")
        repo = TortoiseOcrRepository()

        await repo.write_field(visit.visit_id, "TSH", "2.1", actor)
        await repo.write_field(visit.visit_id, "TSH", "3.4", actor)

        rows = await OcrField.filter(field_type="TSH")
        assert len(rows) == 1, f"줄이 {len(rows)}개다"
        assert rows[0].corrected_value == "3.4"

    async def test_an_empty_value_removes_the_row(self) -> None:
        """**비우면 지운다.** 「빈 값으로 적었다」를 남기면 안 적은 것과 구별이 안 된다."""
        actor, visit = await self.make_world("WF-03")
        repo = TortoiseOcrRepository()
        await repo.write_field(visit.visit_id, "TSH", "2.1", actor)

        field, _ = await repo.write_field(visit.visit_id, "TSH", "  ", actor)

        assert field is None, "지웠는데 값을 돌려준다"
        assert not await OcrField.filter(field_type="TSH").exists(), "지웠는데 줄이 남았다"

    async def test_a_confirmed_field_is_not_overwritten(self) -> None:
        """**확정된 값은 이 길로도 못 고친다.**

        고치기(PATCH)가 막는 것을 여기서 안 막으면, 확정한 값을 우회로 덮어쓸
        수 있다 — 확정은 「이 값으로 안내문을 만든다」는 뜻이라 그러면 안 된다.
        """
        actor, visit = await self.make_world("WF-04")
        repo = TortoiseOcrRepository()
        await repo.write_field(visit.visit_id, "TSH", "2.1", actor)

        row = await OcrField.get(field_type="TSH")
        row.is_confirmed = True
        await row.save(update_fields=["is_confirmed"])

        try:
            await repo.write_field(visit.visit_id, "TSH", "9.9", actor)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409, f"막긴 했는데 {exc} 다"
        else:
            raise AssertionError("확정된 값이 덮어써졌다")

        again = await OcrField.get(field_type="TSH")
        assert again.corrected_value == "2.1", "막았는데 값이 바뀌었다"

    async def test_a_visit_without_a_reading_is_refused(self) -> None:
        """판독한 적이 없으면 붙일 자리가 없다 — 지어내지 않고 404 다."""
        actor, visit = await self.make_world("WF-05", with_result=False)

        try:
            await TortoiseOcrRepository().write_field(visit.visit_id, "TSH", "2.1", actor)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404, f"막긴 했는데 {exc} 다"
        else:
            raise AssertionError("판독이 없는데 값이 담겼다")

    async def test_a_job_without_a_result_is_refused(self) -> None:
        """**작업은 있는데 결과가 없는** 사이 구간도 막는다.

        판독을 걸어 두고 아직 안 끝난 진료가 여기 온다. 붙일 결과가 없는데
        만들어 버리면 판독이 끝나면서 덮어쓰거나 두 벌이 된다.
        """
        actor, visit = await self.make_world("WF-08", with_result=False)
        await OcrJob.create(
            ocr_job_id="wf-노결과",
            hospital_id=visit.hospital_id,
            visit=visit,
            requested_by=actor.staff_id,
            status=OcrJobStatus.PROCESSING,
        )

        try:
            await TortoiseOcrRepository().write_field(visit.visit_id, "TSH", "2.1", actor)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404, f"막긴 했는데 {exc} 다"
        else:
            raise AssertionError("결과가 없는데 값이 담겼다")

        assert not await OcrField.filter(field_type="TSH").exists(), "막았는데 줄이 생겼다"

    async def test_another_clinic_cannot_write(self) -> None:
        """다른 병원의 진료에는 못 적는다."""
        actor, visit = await self.make_world("WF-06")
        stranger, _ = await self.make_world("WF-07")

        try:
            await TortoiseOcrRepository().write_field(visit.visit_id, "TSH", "2.1", stranger)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404, f"막긴 했는데 {exc} 다"
        else:
            raise AssertionError("다른 병원 진료에 값을 적었다")
