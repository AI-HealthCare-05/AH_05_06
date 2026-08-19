from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class StaffRole(StrEnum):
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    STAFF = "STAFF"


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    LEFT = "left"


@dataclass(frozen=True, slots=True)
class ClinicFixture:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class StaffAccountFixture:
    id: UUID
    clinic_id: UUID
    login_id: str
    name: str
    roles: frozenset[StaffRole]
    status: EmploymentStatus = EmploymentStatus.ACTIVE
    must_change_password: bool = False


@dataclass(frozen=True, slots=True)
class PatientFixture:
    id: UUID
    clinic_id: UUID
    chart_number: str
    name: str
    birth_date: date
    phone_number: str


@dataclass(frozen=True, slots=True)
class VisitFixture:
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    assigned_staff_user_id: UUID
    visited_at: datetime
    scenario: str


@dataclass(frozen=True, slots=True)
class Key36FixtureSet:
    clinics: dict[str, ClinicFixture]
    staff_accounts: dict[str, StaffAccountFixture]
    patients: dict[str, PatientFixture]
    visits: dict[str, VisitFixture]
    test_password: str
