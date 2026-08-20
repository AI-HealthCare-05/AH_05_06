import os
from datetime import date, datetime

from app.tests.fixtures.models import (
    HospitalFixture,
    Key36FixtureSet,
    PatientFixture,
    VisitFixture,
)

TEST_PASSWORD_ENV = "KEY36_TEST_PASSWORD"


def _require_test_password() -> None:
    """Require a development-only seed password without returning or storing it."""
    if not os.getenv(TEST_PASSWORD_ENV):
        raise RuntimeError(f"Set {TEST_PASSWORD_ENV} to a development-only value before creating KEY-36 fixtures")


def build_key36_fixture_set() -> Key36FixtureSet:
    """Build patient/visit fixtures linked to the canonical KEY-10 staff IDs.

    Staff account values and passwords deliberately do not live here. The
    canonical accounts are supplied by KEY-10 (PR #12) as
    ``docs/data/synthetic-staff.csv``. Database identifiers use the frozen
    bigint contract; the deterministic values here are test-only IDs.
    """
    _require_test_password()

    # KEY-10(PR #12)가 직원 계정의 유일한 정본이다. 모듈 수준에서
    # import하지 않아 PR #12 병합 전에도 다른 fixture 테스트 수집은 막지 않는다.
    from app.tests.fixtures.staff import by_id

    hospitals = {
        "hospital_alpha": HospitalFixture(1, "H1", "QA 알파의원"),
        "hospital_beta": HospitalFixture(2, "H2", "QA 베타의원"),
    }
    alpha_id = hospitals["hospital_alpha"].hospital_id
    beta_id = hospitals["hospital_beta"].hospital_id

    staff_accounts = {
        "alpha_staff": by_id("SYN-STAFF-01"),
        "alpha_doctor": by_id("SYN-STAFF-02"),
        "alpha_admin": by_id("SYN-STAFF-04"),
        "alpha_doctor_staff": by_id("SYN-STAFF-05"),
        "alpha_admin_staff": by_id("SYN-STAFF-06"),
        "alpha_new_staff": by_id("SYN-STAFF-09"),
        "alpha_left_staff": by_id("SYN-STAFF-11"),
        "beta_staff": by_id("SYN-STAFF-15"),
        "beta_doctor": by_id("SYN-STAFF-16"),
        "beta_admin": by_id("SYN-STAFF-17"),
    }

    patients = {
        "alpha_patient_pcos": PatientFixture(
            1001,
            alpha_id,
            "QA-A-0001",
            "QA환자A",
            date(1994, 2, 14),
            "01000000001",
        ),
        "alpha_patient_ems": PatientFixture(
            1002,
            alpha_id,
            "QA-A-0002",
            "QA환자B",
            date(1989, 8, 23),
            "01000000002",
        ),
        "alpha_patient_unconfirmed": PatientFixture(
            1003,
            alpha_id,
            "QA-A-0003",
            "QA환자C",
            date(1991, 11, 5),
            "01000000003",
        ),
        "beta_patient_isolation": PatientFixture(
            2001,
            beta_id,
            "QA-B-0001",
            "QA환자D",
            date(1996, 6, 18),
            "01000000004",
        ),
    }

    visits = {
        "alpha_visit_pcos": VisitFixture(
            10001,
            alpha_id,
            patients["alpha_patient_pcos"].patient_id,
            staff_accounts["alpha_doctor"].scenario_id,
            datetime(2026, 8, 18, 9, 0),
            "PCOS_YAZ_SINGLE_DRUG",
        ),
        "alpha_visit_ems": VisitFixture(
            10002,
            alpha_id,
            patients["alpha_patient_ems"].patient_id,
            staff_accounts["alpha_doctor"].scenario_id,
            datetime(2026, 8, 18, 10, 0),
            "ENDOMETRIOSIS_MULTI_DRUG",
        ),
        "alpha_visit_unconfirmed": VisitFixture(
            10003,
            alpha_id,
            patients["alpha_patient_unconfirmed"].patient_id,
            staff_accounts["alpha_doctor"].scenario_id,
            datetime(2026, 8, 18, 11, 0),
            "OCR_UNCONFIRMED",
        ),
        "beta_visit_isolation": VisitFixture(
            20001,
            beta_id,
            patients["beta_patient_isolation"].patient_id,
            staff_accounts["beta_doctor"].scenario_id,
            datetime(2026, 8, 18, 13, 0),
            "CROSS_HOSPITAL_DENY",
        ),
    }

    return Key36FixtureSet(hospitals, staff_accounts, patients, visits)
