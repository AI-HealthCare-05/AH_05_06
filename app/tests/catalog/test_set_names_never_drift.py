"""**처방 세트 이름은 지난 진료기록이 쥔 열쇠다.**

`Prescription.prescription_set` 은 스냅샷 **문자열**이고(KEY-137), 안내 생성이
그 문자열로 세트를 찾아 문구를 붙인다 — `app/services/guides.py` 와
`app/services/drug_caution.py` 의 `filter(name=…)`.

그래서 이름이 어긋나면 **그 진료들의 안내문 문구가 통째로 떨어져 나간다.**
터지지 않는다. 승인 문구도 의사가 고친 문구도 안 붙고 범용 문장이 나가는데,
남는 것은 로그 한 줄뿐이고 화면은 아무 말도 안 한다.

실제로 한 번 벌어졌다(2026-09-02). 설정 화면에 이름 편집이 잠깐 열려 있던
사이 세트 하나가 「(처음)」에서 「(처음1)」로 바뀌었고, 그 이름을 든 진료
10건이 짝을 잃었다. 코드는 되돌렸지만 **어긋남을 알아채는 것이 아무것도
없었다** — 이 파일이 그것이다.
"""

from datetime import UTC, datetime

from tortoise.exceptions import IntegrityError

from app.models.catalog import PrescriptionSet
from app.models.patients import Patient
from app.models.prescriptions import Prescription
from app.models.visits import Visit
from app.tests.catalog.test_prescription_settings import PrescriptionSettingsTestCase, a_plan


class SetNamesNeverDriftTestCase(PrescriptionSettingsTestCase):
    async def a_visit_pointing_at(self, row: PrescriptionSet, staff) -> Prescription:
        """그 세트 이름을 **스냅샷으로 든** 진료 하나."""
        patient = await Patient.create(
            hospital_id=staff.hospital_id,
            hospital_patient_no="DRIFT-1",
            name="합성환자",
            birth_date="1990-05-15",
            phone="01012345678",
            sms_consent=True,
        )
        visit = await Visit.create(
            hospital_id=staff.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        )
        return await Prescription.create(visit=visit, prescription_set=row.name)

    async def test_saving_everything_else_leaves_the_snapshot_resolvable(self) -> None:
        """**설정을 통째로 저장해도 지난 진료기록이 세트를 계속 찾는다.**

        이것이 이름을 잠근 까닭 그 자체다. 저장이 이름을 건드리면 스냅샷이
        허공을 가리키고, 안내문 문구가 조용히 범용으로 바뀐다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])
        snapshot = await self.a_visit_pointing_at(row, staff)

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(disease="PCOS", days_mode="PACK", days_per_pack=28),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 200, answer.text
        found = await PrescriptionSet.filter(name=snapshot.prescription_set).first()
        assert found is not None, "저장 뒤 스냅샷이 세트를 못 찾는다 — 문구가 조용히 떨어진다"
        assert found.prescription_set_id == row.prescription_set_id

    async def test_two_sets_cannot_share_a_name(self) -> None:
        """**같은 이름이 둘이면 어느 세트로 풀릴지 모른다.**

        `filter(name=…).first()` 에는 `ORDER BY` 가 없다(tortoise). 인덱스나
        옵티마이저가 바뀌면 같은 진료기록이 어제와 다른 세트로 풀린다 —
        재현되지 않는 의료 내용 오류다. 그래서 숨긴 이름도 재사용하지 않는다.
        """
        row = await self.a_furnished_set()

        try:
            await PrescriptionSet.create(name=row.name)
        except IntegrityError:
            pass
        else:
            raise AssertionError("같은 이름의 세트가 둘 만들어졌다 — unique 가 풀렸다")

    async def test_the_unique_guard_is_declared(self) -> None:
        """모델에서 `unique` 가 사라지면 위 검사가 조용히 통과할 수 있다."""
        assert PrescriptionSet._meta.fields_map["name"].unique, "name 의 unique 가 풀렸다"
