from uuid import UUID

import pytest

from app.tests.fixtures.key36 import build_key36_fixture_set
from app.tests.fixtures.models import EmploymentStatus, StaffRole


@pytest.fixture
def key36_fixtures(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("KEY36_TEST_PASSWORD", "in-memory-development-secret")
    return build_key36_fixture_set()


def test_fixture_set_contains_required_role_accounts(key36_fixtures):
    accounts = key36_fixtures.staff_accounts

    assert accounts["alpha_admin"].roles == {StaffRole.ADMIN}
    assert accounts["alpha_doctor"].roles == {StaffRole.DOCTOR}
    assert accounts["alpha_staff"].roles == {StaffRole.STAFF}
    assert accounts["alpha_admin_staff"].roles == {StaffRole.ADMIN, StaffRole.STAFF}


def test_fixture_identifiers_are_uuid(key36_fixtures):
    entities = (
        *key36_fixtures.clinics.values(),
        *key36_fixtures.staff_accounts.values(),
        *key36_fixtures.patients.values(),
        *key36_fixtures.visits.values(),
    )

    assert all(isinstance(entity.id, UUID) for entity in entities)


def test_patient_visits_are_linked_to_same_clinic_accounts(key36_fixtures):
    patients_by_id = {patient.id: patient for patient in key36_fixtures.patients.values()}
    staff_by_id = {staff.id: staff for staff in key36_fixtures.staff_accounts.values()}

    for visit in key36_fixtures.visits.values():
        assert patients_by_id[visit.patient_id].clinic_id == visit.clinic_id
        assert staff_by_id[visit.assigned_staff_user_id].clinic_id == visit.clinic_id


def test_cross_clinic_fixture_supports_rbac_denial(key36_fixtures):
    alpha_staff = key36_fixtures.staff_accounts["alpha_staff"]
    beta_patient = key36_fixtures.patients["beta_patient_isolation"]

    assert alpha_staff.clinic_id != beta_patient.clinic_id


def test_inactive_and_first_login_accounts_are_available(key36_fixtures):
    accounts = key36_fixtures.staff_accounts

    assert accounts["alpha_left_staff"].status is EmploymentStatus.LEFT
    assert accounts["alpha_new_staff"].must_change_password is True


def test_fixture_password_is_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("KEY36_TEST_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="KEY36_TEST_PASSWORD"):
        build_key36_fixture_set()


def test_fixture_is_blocked_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("KEY36_TEST_PASSWORD", "must-not-be-used")

    with pytest.raises(RuntimeError, match="production"):
        build_key36_fixture_set()
