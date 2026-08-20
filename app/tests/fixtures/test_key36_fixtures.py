import pytest

from app.tests.fixtures.key36 import build_key36_fixture_set


@pytest.fixture
def key36_fixtures():
    return build_key36_fixture_set()


def test_required_roles_reference_canonical_key10_accounts(key36_fixtures):
    accounts = key36_fixtures.staff_accounts
    assert accounts["alpha_admin"].roles == {"admin"}
    assert accounts["alpha_doctor"].roles == {"doctor"}
    assert accounts["alpha_staff"].roles == {"staff"}
    assert accounts["alpha_admin_staff"].roles == {"admin", "staff"}
    assert accounts["beta_staff"].hospital == "H2"


def test_fixture_identifiers_are_bigint_compatible_and_unique(key36_fixtures):
    hospital_ids = [hospital.hospital_id for hospital in key36_fixtures.hospitals.values()]
    patient_ids = [patient.patient_id for patient in key36_fixtures.patients.values()]
    visit_ids = [visit.visit_id for visit in key36_fixtures.visits.values()]

    for identifiers in (hospital_ids, patient_ids, visit_ids):
        assert all(isinstance(identifier, int) and identifier > 0 for identifier in identifiers)
        assert len(identifiers) == len(set(identifiers))


def test_patient_visits_are_linked_to_same_hospital_and_known_doctor(key36_fixtures):
    patients_by_id = {patient.patient_id: patient for patient in key36_fixtures.patients.values()}
    doctors_by_id = {
        staff.scenario_id: staff for staff in key36_fixtures.staff_accounts.values() if "doctor" in staff.roles
    }
    hospital_codes_by_id = {hospital.hospital_id: hospital.code for hospital in key36_fixtures.hospitals.values()}

    for visit in key36_fixtures.visits.values():
        assert patients_by_id[visit.patient_id].hospital_id == visit.hospital_id
        assert doctors_by_id[visit.doctor_scenario_id].hospital == hospital_codes_by_id[visit.hospital_id]


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
