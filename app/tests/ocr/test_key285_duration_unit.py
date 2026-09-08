"""사람이 처방일수의 단위를 고칠 수 있다 — KEY-285.

KEY-271 로 `OcrField.unit` 이 **소진 예정일 셈에 실제로 쓰이기 시작했다.**
「3」이 3통이면 84일, 3일이면 3일이다 — 그 차이가 81일이다.

그런데 그 칸을 사람이 고칠 길이 없었다. 보정(PATCH)도 직접입력도 `unit` 을 안
받아서, 잘못 심긴 단위는 **DB 를 직접 만져야** 풀렸다 (이희진 님 `#236` 리뷰 ④).

여기서 지키는 것은 셋이다.

    고칠 수 있다      값을 다시 안 적어도 단위만 바꿀 수 있다
    끝까지 따라간다   고친 단위가 처방 행의 일수까지 바뀐다
    아무 데나 안 붙는다  검사값 줄에 「통」이 박히면 그 글자가 화면에 그대로 뜬다
"""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from tortoise.contrib.test import TestCase

from app.models.ocr import (
    DurationUnit,
    OcrField,
    OcrJob,
    OcrJobStatus,
    OcrResult,
)
from app.models.patients import Patient
from app.models.prescriptions import PrescriptionItem
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.schemas import UpdateOcrFieldRequest, WriteOcrFieldRequest
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository

HOSPITAL = 6285
ACTOR = OcrActor(staff_id=628501, hospital_id=HOSPITAL, roles=frozenset({"staff"}))


class DurationUnitTestCase(TestCase):
    async def make_result(self) -> OcrResult:
        patient = await Patient.create(
            hospital_id=HOSPITAL,
            hospital_patient_no="SYN-KEY285-01",
            name="합성환자",
            birth_date=date(1990, 5, 15),
            phone="01012345678",
        )
        self.visit = await Visit.create(
            hospital_id=HOSPITAL,
            patient=patient,
            visited_at=datetime(2026, 9, 7, 0, 0, tzinfo=UTC),
        )
        job = await OcrJob.create(
            ocr_job_id="ocr_key285_01",
            hospital_id=HOSPITAL,
            visit_id=self.visit.visit_id,
            requested_by=ACTOR.staff_id,
            status=OcrJobStatus.COMPLETED,
        )
        return await OcrResult.create(ocr_job=job, model_name="synthetic-key285")

    async def make_field(
        self,
        result: OcrResult,
        field_type: str,
        value: str,
        *,
        is_confirmed: bool = False,
        confirmed_by: int | None = None,
        confirmed_at: datetime | None = None,
    ) -> OcrField:
        return await OcrField.create(
            ocr_result=result,
            field_type=field_type,
            extracted_value=value,
            is_confirmed=is_confirmed,
            confirmed_by=confirmed_by,
            confirmed_at=confirmed_at,
        )

    async def test_the_unit_can_be_changed_without_retyping_the_number(self) -> None:
        """**인수조건 ①** — 숫자는 맞고 단위만 틀린 것이 이 칸이 생긴 까닭이다.

        `corrected_value` 를 함께 요구하면 스탭이 같은 숫자를 굳이 다시 적어야
        하고, 그러다 오타가 나면 고치러 왔다가 값을 망친다.
        """
        result = await self.make_result()
        field = await self.make_field(result, "DURATION_DAYS", "3")
        repository = TortoiseOcrRepository()

        saved, _ = await repository.update_field(
            field.ocr_field_id,
            UpdateOcrFieldRequest(base_version=1, unit=DurationUnit.PACK),
            ACTOR,
        )

        assert saved.unit == "통"
        assert saved.value == "3", "숫자를 건드리면 안 된다"
        assert saved.version == 2, "판올림이 없으면 다음 저장이 옛 판을 덮는다"
        assert saved.modified_by == ACTOR.staff_id, "누가 고쳤는지가 안 남았다"

    async def test_changing_the_unit_drops_the_confirmation_stamp(self) -> None:
        """**단위를 고치는 것은 값을 고치는 것이다.**

        숫자가 그대로여도 소진 예정일이 통째로 바뀐다(3 → 84). 확정 도장을
        남겨 두면 「확정했다」가 **확정한 사람이 못 본 일수**를 가리키게 된다.
        """
        result = await self.make_result()
        field = await self.make_field(
            result,
            "DURATION_DAYS",
            "3",
            is_confirmed=True,
            confirmed_by=ACTOR.staff_id,
            confirmed_at=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
        )
        repository = TortoiseOcrRepository()

        saved, _ = await repository.update_field(
            field.ocr_field_id,
            UpdateOcrFieldRequest(base_version=1, unit=DurationUnit.PACK),
            ACTOR,
        )

        assert saved.is_confirmed is False, "확정 도장이 남으면 아무도 다시 안 본다"
        assert saved.confirmed_by is None
        assert saved.confirmed_at is None

    async def test_the_fixed_unit_reaches_the_prescription_row(self) -> None:
        """**인수조건 ②** — 고친 값이 소진 셈까지 간다.

        화면에서 고쳐지기만 하고 `finalize_ocr` 이 옛 단위를 쓰면, 사람은
        고쳤다고 믿는데 문자는 여전히 엉뚱한 날 나간다.
        """
        result = await self.make_result()
        await self.make_field(result, "MEDICATION_NAME", "야즈정")
        await self.make_field(result, "FREQUENCY", "1일 1회")
        await self.make_field(result, "PRESCRIPTION_SET", "PCOS · 야즈 (처음)")
        days = await self.make_field(result, "DURATION_DAYS", "3")
        for field in await OcrField.all():
            field.is_confirmed = True
            await field.save()
        repository = TortoiseOcrRepository()

        await repository.update_field(
            days.ocr_field_id,
            UpdateOcrFieldRequest(base_version=1, unit=DurationUnit.PACK, confirm=True),
            ACTOR,
        )
        await repository.finalize_ocr(self.visit.visit_id, ACTOR)

        item = await PrescriptionItem.all().first()
        assert item is not None
        assert item.duration_days == 84, f"3통을 84일로 안 셌다 — {item.duration_days}"

    async def test_a_lab_row_refuses_a_unit(self) -> None:
        """**검사값 줄에는 안 붙는다.**

        화면의 `fieldUnit` 이 **서버가 준 단위를 무조건 우선한다**. 헤모글로빈
        줄에 「통」이 박히면 그 글자가 그대로 사람 눈에 붙고, 같은 항목이
        진료마다 다른 단위로 보인다.
        """
        result = await self.make_result()
        field = await self.make_field(result, "HEMOGLOBIN", "10.2")
        repository = TortoiseOcrRepository()

        with pytest.raises(OcrApiError) as caught:
            await repository.update_field(
                field.ocr_field_id,
                UpdateOcrFieldRequest(base_version=1, unit=DurationUnit.PACK),
                ACTOR,
            )

        assert caught.value.code == "UNIT_NOT_ALLOWED"
        assert (await OcrField.get(ocr_field_id=field.ocr_field_id)).unit is None

    async def test_the_second_drug_row_takes_one_too(self) -> None:
        """둘째 약도 제 총투를 갖는다 — 접미사가 붙을 뿐 같은 칸이다."""
        result = await self.make_result()
        field = await self.make_field(result, "DURATION_DAYS_2", "2")
        repository = TortoiseOcrRepository()

        saved, _ = await repository.update_field(
            field.ocr_field_id,
            UpdateOcrFieldRequest(base_version=1, unit=DurationUnit.PACK),
            ACTOR,
        )

        assert saved.unit == "통"

    async def test_writing_a_missing_value_can_say_the_unit(self) -> None:
        """직접입력에도 단위가 붙는다 — 「3」만 적으면 3일로 읽힌다."""
        await self.make_result()
        repository = TortoiseOcrRepository()

        saved, _ = await repository.write_field(
            self.visit.visit_id,
            "DURATION_DAYS",
            "3",
            ACTOR,
            unit=DurationUnit.PACK.value,
        )

        assert saved is not None
        assert saved.unit == "통"
        assert saved.value == "3"

    async def test_writing_a_lab_value_refuses_a_unit(self) -> None:
        """두 길이 같은 문을 지난다 — 한쪽만 막으면 다른 쪽으로 들어온다."""
        result = await self.make_result()
        await self.make_field(result, "HEMOGLOBIN", "10.2")
        repository = TortoiseOcrRepository()

        with pytest.raises(OcrApiError) as caught:
            await repository.write_field(self.visit.visit_id, "HEMOGLOBIN", "9.8", ACTOR, unit="통")

        assert caught.value.code == "UNIT_NOT_ALLOWED"


class DurationUnitContractTestCase(TestCase):
    """DTO 가 값의 **모양**을 막는다 — 서비스가 붙일 **자리**를 막는 것과 짝이다."""

    async def test_an_unknown_unit_is_refused_at_the_door(self) -> None:
        """**인수조건 ③** — 모르는 단위를 조용히 저장하지 않는다."""
        for bogus in ("정", "박스", "일수", "days", ""):
            with pytest.raises(ValidationError):
                UpdateOcrFieldRequest(base_version=1, unit=bogus)  # type: ignore[arg-type]

    async def test_a_unit_alone_is_a_complete_request(self) -> None:
        """단위만 보내는 것이 이 티켓의 한복판이다 — 「수정값을 고르세요」로 막히면 안 된다."""
        request = UpdateOcrFieldRequest(base_version=1, unit=DurationUnit.DAYS)
        assert request.unit is DurationUnit.DAYS
        assert request.corrected_value is None

    async def test_nothing_at_all_is_still_refused(self) -> None:
        """단위를 원천으로 인정하면서 **빈 요청까지 열리면** 안 된다."""
        with pytest.raises(ValidationError):
            UpdateOcrFieldRequest(base_version=1)

    async def test_the_write_path_takes_the_same_two_values(self) -> None:
        assert WriteOcrFieldRequest(value="3", unit=DurationUnit.PACK).unit is DurationUnit.PACK
        with pytest.raises(ValidationError):
            WriteOcrFieldRequest(value="3", unit="박스")  # type: ignore[arg-type]
