import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.repositories.visit_repository import VisitRepository
from app.tests.fixtures.staff import all_staff
from scripts.seed import SeedDataError, _doctor_ids_by_name, _patient_values, _validate_patient_rows

PATIENT_CSV = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-patients.csv"


def patient_rows() -> list[dict[str, str]]:
    with PATIENT_CSV.open(encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def test_normal_patient_visit_scenario_resolves_to_h1_doctor() -> None:
    row = next(row for row in patient_rows() if row["시나리오ID"] == "SYN-EMS-01")
    h1_doctors = {staff.name for staff in all_staff() if staff.hospital == "H1" and "doctor" in staff.roles}

    assert row["진료일"]
    assert row["담당의"] in h1_doctors


def test_patient_seed_values_follow_api_phone_storage_contract() -> None:
    row = next(row for row in patient_rows() if row["시나리오ID"] == "SYN-EMS-01")

    values = _patient_values(row)

    assert values["phone"] == "01024317788"
    assert "-" not in str(values["phone"])


def test_doctor_mapping_excludes_non_doctor_accounts() -> None:
    rows = [
        SimpleNamespace(staff_id=11, name="합성의사", roles=["doctor"]),
        SimpleNamespace(staff_id=12, name="합성스탭", roles=["staff"]),
    ]

    assert _doctor_ids_by_name(rows) == {"합성의사": 11}


def test_ambiguous_same_hospital_doctor_name_is_rejected() -> None:
    rows = [
        SimpleNamespace(staff_id=21, name="동명이인의사", roles=["doctor"]),
        SimpleNamespace(staff_id=22, name="동명이인의사", roles=["doctor"]),
    ]

    with pytest.raises(SeedDataError, match="동명이인 의사"):
        _doctor_ids_by_name(rows)


def test_missing_doctor_is_rejected_during_prevalidation() -> None:
    row = next(row for row in patient_rows() if row["시나리오ID"] == "SYN-EMS-01")

    with pytest.raises(SeedDataError, match="H1 의사에서 찾을 수 없음"):
        _validate_patient_rows([row], doctor_map={})


def test_conflicting_patient_identity_for_same_chart_is_rejected() -> None:
    row = next(row for row in patient_rows() if row["시나리오ID"] == "SYN-EMS-01")
    conflicting = {**row, "이름": "다른합성환자"}

    with pytest.raises(SeedDataError, match="환자 정보가 서로 다름"):
        _validate_patient_rows([row, conflicting], doctor_map={row["담당의"]: 11})


def test_every_visit_row_has_an_h1_doctor_and_unique_patient_identity() -> None:
    rows = patient_rows()
    visits = [row for row in rows if row["진료일"].strip()]
    h1_doctors = {staff.name for staff in all_staff() if staff.hospital == "H1" and "doctor" in staff.roles}

    assert len(rows) == len({row["시나리오ID"] for row in rows}) == 100
    assert len(rows) == len({row["차트번호"] for row in rows}) == 100
    assert len(visits) == 99
    assert all(row["담당의"] in h1_doctors for row in visits)


@pytest.mark.asyncio
@pytest.mark.parametrize(("patient_hospital_id", "is_visible"), [(1, True), (2, False)])
async def test_visit_repository_rejects_cross_hospital_patient_relation(
    monkeypatch: pytest.MonkeyPatch,
    patient_hospital_id: int,
    is_visible: bool,
) -> None:
    class FakeVisit:
        patient = SimpleNamespace(hospital_id=patient_hospital_id)

        async def fetch_related(self, relation: str) -> None:
            assert relation == "patient"

    visit = FakeVisit()

    async def fake_get_or_none(**filters: int) -> FakeVisit:
        assert filters == {"visit_id": 501, "hospital_id": 1}
        return visit

    monkeypatch.setattr("app.repositories.visit_repository.Visit.get_or_none", fake_get_or_none)

    result = await VisitRepository().get_scoped(visit_id=501, hospital_id=1)

    assert (result is visit) is is_visible
