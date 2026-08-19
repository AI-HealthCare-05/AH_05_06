import os
from datetime import date, datetime
from uuid import UUID

from app.tests.fixtures.models import (
    ClinicFixture,
    EmploymentStatus,
    Key36FixtureSet,
    PatientFixture,
    StaffAccountFixture,
    StaffRole,
    VisitFixture,
)

TEST_PASSWORD_ENV = "KEY36_TEST_PASSWORD"
APP_ENV_NAME = "APP_ENV"
PRODUCTION_ENV_NAMES = frozenset({"prod", "production"})


def _uuid(value: str) -> UUID:
    return UUID(value)


def _load_test_password() -> str:
    if os.getenv(APP_ENV_NAME, "local").lower() in PRODUCTION_ENV_NAMES:
        raise RuntimeError("KEY-36 fixtures must never run in a production environment")

    password = os.getenv(TEST_PASSWORD_ENV)
    if not password:
        raise RuntimeError(f"Set {TEST_PASSWORD_ENV} to a development-only value before creating KEY-36 fixtures")
    return password


def build_key36_fixture_set() -> Key36FixtureSet:
    """Build deterministic, synthetic UUID fixtures for auth and RBAC tests."""
    test_password = _load_test_password()

    clinics = {
        "clinic_alpha": ClinicFixture(_uuid("10000000-0000-4000-8000-000000000001"), "QA 알파의원"),
        "clinic_beta": ClinicFixture(_uuid("20000000-0000-4000-8000-000000000001"), "QA 베타의원"),
    }
    alpha_id = clinics["clinic_alpha"].id
    beta_id = clinics["clinic_beta"].id

    staff_accounts = {
        "alpha_admin": StaffAccountFixture(
            _uuid("11000000-0000-4000-8000-000000000001"),
            alpha_id,
            "qa_alpha_admin",
            "QA알파관리자",
            frozenset({StaffRole.ADMIN}),
        ),
        "alpha_doctor": StaffAccountFixture(
            _uuid("11000000-0000-4000-8000-000000000002"),
            alpha_id,
            "qa_alpha_doctor",
            "QA알파의사",
            frozenset({StaffRole.DOCTOR}),
        ),
        "alpha_staff": StaffAccountFixture(
            _uuid("11000000-0000-4000-8000-000000000003"),
            alpha_id,
            "qa_alpha_staff",
            "QA알파스탭",
            frozenset({StaffRole.STAFF}),
        ),
        "alpha_admin_staff": StaffAccountFixture(
            _uuid("11000000-0000-4000-8000-000000000004"),
            alpha_id,
            "qa_alpha_admin_staff",
            "QA알파복수역할",
            frozenset({StaffRole.ADMIN, StaffRole.STAFF}),
        ),
        "alpha_left_staff": StaffAccountFixture(
            _uuid("11000000-0000-4000-8000-000000000005"),
            alpha_id,
            "qa_alpha_left_staff",
            "QA알파퇴사스탭",
            frozenset({StaffRole.STAFF}),
            EmploymentStatus.LEFT,
        ),
        "alpha_new_staff": StaffAccountFixture(
            _uuid("11000000-0000-4000-8000-000000000006"),
            alpha_id,
            "qa_alpha_new_staff",
            "QA알파신규스탭",
            frozenset({StaffRole.STAFF}),
            must_change_password=True,
        ),
        "beta_admin": StaffAccountFixture(
            _uuid("21000000-0000-4000-8000-000000000001"),
            beta_id,
            "qa_beta_admin",
            "QA베타관리자",
            frozenset({StaffRole.ADMIN}),
        ),
        "beta_doctor": StaffAccountFixture(
            _uuid("21000000-0000-4000-8000-000000000002"),
            beta_id,
            "qa_beta_doctor",
            "QA베타의사",
            frozenset({StaffRole.DOCTOR}),
        ),
        "beta_staff": StaffAccountFixture(
            _uuid("21000000-0000-4000-8000-000000000003"),
            beta_id,
            "qa_beta_staff",
            "QA베타스탭",
            frozenset({StaffRole.STAFF}),
        ),
    }

    patients = {
        "alpha_patient_pcos": PatientFixture(
            _uuid("12000000-0000-4000-8000-000000000001"),
            alpha_id,
            "QA-A-0001",
            "QA환자A",
            date(1994, 2, 14),
            "01000000001",
        ),
        "alpha_patient_ems": PatientFixture(
            _uuid("12000000-0000-4000-8000-000000000002"),
            alpha_id,
            "QA-A-0002",
            "QA환자B",
            date(1989, 8, 23),
            "01000000002",
        ),
        "alpha_patient_unconfirmed": PatientFixture(
            _uuid("12000000-0000-4000-8000-000000000003"),
            alpha_id,
            "QA-A-0003",
            "QA환자C",
            date(1991, 11, 5),
            "01000000003",
        ),
        "beta_patient_isolation": PatientFixture(
            _uuid("22000000-0000-4000-8000-000000000001"),
            beta_id,
            "QA-B-0001",
            "QA환자D",
            date(1996, 6, 18),
            "01000000004",
        ),
    }

    visits = {
        "alpha_visit_pcos": VisitFixture(
            _uuid("13000000-0000-4000-8000-000000000001"),
            alpha_id,
            patients["alpha_patient_pcos"].id,
            staff_accounts["alpha_staff"].id,
            datetime(2026, 8, 18, 9, 0),
            "PCOS_YAZ_SINGLE_DRUG",
        ),
        "alpha_visit_ems": VisitFixture(
            _uuid("13000000-0000-4000-8000-000000000002"),
            alpha_id,
            patients["alpha_patient_ems"].id,
            staff_accounts["alpha_doctor"].id,
            datetime(2026, 8, 18, 10, 0),
            "ENDOMETRIOSIS_MULTI_DRUG",
        ),
        "alpha_visit_unconfirmed": VisitFixture(
            _uuid("13000000-0000-4000-8000-000000000003"),
            alpha_id,
            patients["alpha_patient_unconfirmed"].id,
            staff_accounts["alpha_admin_staff"].id,
            datetime(2026, 8, 18, 11, 0),
            "OCR_UNCONFIRMED",
        ),
        "beta_visit_isolation": VisitFixture(
            _uuid("23000000-0000-4000-8000-000000000001"),
            beta_id,
            patients["beta_patient_isolation"].id,
            staff_accounts["beta_staff"].id,
            datetime(2026, 8, 18, 13, 0),
            "CROSS_CLINIC_DENY",
        ),
    }

    return Key36FixtureSet(clinics, staff_accounts, patients, visits, test_password)
