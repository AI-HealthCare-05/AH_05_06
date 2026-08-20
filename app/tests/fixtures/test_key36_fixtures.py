from pathlib import Path

import pytest

from app.tests.fixtures.key36 import build_key36_fixture_set

STAFF_LOADER = Path(__file__).with_name("staff.py")


@pytest.fixture
def key36_fixtures(monkeypatch: pytest.MonkeyPatch):
    if not STAFF_LOADER.exists():
        pytest.skip("KEY-10(PR #12) 직원 fixture 병합 후 실행한다")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("KEY36_TEST_PASSWORD", "in-memory-development-secret")
    return build_key36_fixture_set()


def test_required_roles_reference_canonical_key10_accounts(key36_fixtures):
    accounts = key36_fixtures.staff_accounts
    assert accounts["alpha_admin"].roles == {"admin"}
    assert accounts["alpha_doctor"].roles == {"doctor"}
    assert accounts["alpha_staff"].roles == {"staff"}
    assert accounts["alpha_admin_staff"].roles == {"admin", "staff"}
    assert accounts["beta_staff"].hospital == "H2"


def test_fixture_identifiers_are_bigint_compatible_and_unique(key36_fixtures):
    entities = (
        *key36_fixtures.hospitals.values(),
        *key36_fixtures.patients.values(),
        *key36_fixtures.visits.values(),
    )
    identifiers = [
        entity.hospital_id
        if hasattr(entity, "hospital_id") and not hasattr(entity, "patient_id")
        else entity.patient_id
        if hasattr(entity, "patient_id") and not hasattr(entity, "visit_id")
        else entity.visit_id
        for entity in entities
    ]

    assert all(isinstance(identifier, int) and identifier > 0 for identifier in identifiers)
    assert len(identifiers) == len(set(identifiers))


def test_patient_visits_are_linked_to_same_hospital_and_known_doctor(key36_fixtures):
    patients_by_id = {patient.patient_id: patient for patient in key36_fixtures.patients.values()}
    known_doctor_ids = {
        staff.scenario_id for staff in key36_fixtures.staff_accounts.values() if "doctor" in staff.roles
    }

    for visit in key36_fixtures.visits.values():
        assert patients_by_id[visit.patient_id].hospital_id == visit.hospital_id
        assert visit.doctor_scenario_id in known_doctor_ids


def test_fixture_contains_normal_and_unconfirmed_patient_flows(key36_fixtures):
    assert set(key36_fixtures.visits) == {
        "alpha_visit_pcos",
        "alpha_visit_ems",
        "alpha_visit_unconfirmed",
        "beta_visit_isolation",
    }
    assert key36_fixtures.visits["alpha_visit_unconfirmed"].scenario == "OCR_UNCONFIRMED"


def test_cross_hospital_fixture_supports_rbac_denial(key36_fixtures):
    alpha_staff = key36_fixtures.staff_accounts["alpha_staff"]
    beta_staff = key36_fixtures.staff_accounts["beta_staff"]
    beta_patient = key36_fixtures.patients["beta_patient_isolation"]

    assert alpha_staff.hospital == "H1"
    assert beta_staff.hospital == "H2"
    assert beta_patient.hospital_id == key36_fixtures.hospitals["hospital_beta"].hospital_id


def test_fixture_contains_no_password(key36_fixtures):
    assert not hasattr(key36_fixtures, "test_password")


def test_fixture_requires_a_development_password(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("KEY36_TEST_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="KEY36_TEST_PASSWORD"):
        build_key36_fixture_set()
