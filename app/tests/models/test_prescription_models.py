"""처방 표가 복약안내의 근거를 실제로 담는가 — KEY-137.

확인하는 것은 넷이다.

    ① 한 진료의 처방에 약이 여럿 붙는다 — CSV 가 ` + ` 로 눌러 담은 것을 갈라 넣는다
    ② `필요시` 약에는 기간이 없다 — 「진통제를 84일간」이 되지 않게
    ③ 병원 격리가 `visit` 을 타고 선다 — `hospital_id` 사본 없이
    ④ 진료가 지워지면 처방도 함께 지워진다
"""

from datetime import datetime

from tortoise.contrib.test import TestCase

from app.models.patients import Patient
from app.models.prescriptions import AS_NEEDED, Prescription, PrescriptionItem
from app.models.visits import Visit

HOSPITAL = 1
OTHER_HOSPITAL = 2
VISITED_AT = datetime.fromisoformat("2026-08-20T12:00:00+09:00")


async def _visit(hospital_id: int = HOSPITAL, chart_no: str = "SYN-137-01") -> Visit:
    patient = await Patient.create(
        hospital_id=hospital_id,
        hospital_patient_no=chart_no,
        name="합성처방환자",
        birth_date="1993-05-05",
        gender="FEMALE",
        phone="01000001370",
        sms_consent=True,
    )
    return await Visit.create(hospital_id=hospital_id, patient=patient, visited_at=VISITED_AT)


async def _prescription(visit: Visit, label: str = "자궁내막증 · 비잔 (계속)") -> Prescription:
    return await Prescription.create(visit=visit, prescription_set=label)


class TestOnePrescriptionHoldsManyDrugs(TestCase):
    async def test_two_items_hang_off_one_prescription(self) -> None:
        """CSV 의 "비잔정 2mg + 진통제" 가 두 줄이 되어야 한다.

        한 줄에 눌러 두면 「두 번째 약의 용법」을 꺼낼 수 없다.
        """
        prescription = await _prescription(await _visit())
        await PrescriptionItem.create(
            prescription=prescription, name="비잔정 2mg", frequency="1일 1회", duration_days=84
        )
        await PrescriptionItem.create(prescription=prescription, name="진통제", frequency=AS_NEEDED)

        items = await PrescriptionItem.filter(prescription=prescription).order_by("prescription_item_id")
        assert [i.name for i in items] == ["비잔정 2mg", "진통제"]
        assert [i.frequency for i in items] == ["1일 1회", AS_NEEDED]

    async def test_the_set_label_is_kept_as_written(self) -> None:
        """세트 이름은 id 가 아니라 그때의 이름 스냅샷이다."""
        prescription = await _prescription(await _visit(), "PCOS · 야즈 + 메트포르민")
        stored = await Prescription.get(prescription_id=prescription.prescription_id)
        assert stored.prescription_set == "PCOS · 야즈 + 메트포르민"


class TestAsNeededDrugsCarryNoDuration(TestCase):
    """`필요시` 약에 기간이 붙으면 안내문이 틀린 말을 한다."""

    async def test_duration_stays_empty_for_as_needed(self) -> None:
        prescription = await _prescription(await _visit())
        item = await PrescriptionItem.create(prescription=prescription, name="진통제", frequency=AS_NEEDED)

        stored = await PrescriptionItem.get(prescription_item_id=item.prescription_item_id)
        assert stored.duration_days is None

    async def test_scheduled_drugs_keep_their_duration_as_an_integer(self) -> None:
        """소진예정일을 계산하려면 정수여야 한다 — 문자열이면 더할 수 없다."""
        prescription = await _prescription(await _visit())
        item = await PrescriptionItem.create(
            prescription=prescription, name="비잔정 2mg", frequency="1일 1회", duration_days=84
        )

        stored = await PrescriptionItem.get(prescription_item_id=item.prescription_item_id)
        assert stored.duration_days == 84
        assert isinstance(stored.duration_days, int)


class TestHospitalIsolationRidesOnTheVisit(TestCase):
    """`prescription` 은 `hospital_id` 사본을 들지 않는다. 진료를 타고 판단한다."""

    async def test_other_hospital_prescription_is_not_reachable(self) -> None:
        ours = await _prescription(await _visit(HOSPITAL, "SYN-137-10"))
        theirs = await _prescription(await _visit(OTHER_HOSPITAL, "SYN-137-11"))

        visible = await Prescription.filter(visit__hospital_id=HOSPITAL)
        ids = {p.prescription_id for p in visible}
        assert ours.prescription_id in ids
        assert theirs.prescription_id not in ids, "타 병원 처방이 보인다"

    async def test_items_are_scoped_through_two_hops(self) -> None:
        theirs = await _prescription(await _visit(OTHER_HOSPITAL, "SYN-137-20"))
        await PrescriptionItem.create(prescription=theirs, name="야즈정", frequency="1일 1회", duration_days=28)

        leaked = await PrescriptionItem.filter(prescription__visit__hospital_id=HOSPITAL)
        assert leaked == [], "타 병원 처방 항목이 보인다"


class TestDeletingAVisitTakesThePrescriptionWithIt(TestCase):
    async def test_cascade_reaches_items_too(self) -> None:
        """진료가 사라지면 그 처방과 약 줄도 남지 않는다.

        남겨 두면 어느 진료의 것인지 모르는 처방이 떠돈다.
        """
        visit = await _visit(chart_no="SYN-137-30")
        prescription = await _prescription(visit)
        await PrescriptionItem.create(
            prescription=prescription, name="비잔정 2mg", frequency="1일 1회", duration_days=56
        )

        await visit.delete()

        assert await Prescription.filter(prescription_id=prescription.prescription_id).count() == 0
        assert await PrescriptionItem.filter(prescription_id=prescription.prescription_id).count() == 0
