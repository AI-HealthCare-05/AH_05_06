from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tests.fixtures.staff import Staff


@dataclass(frozen=True, slots=True)
class HospitalFixture:
    hospital_id: int
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class PatientFixture:
    patient_id: int
    hospital_id: int
    chart_number: str
    name: str
    birth_date: date
    phone_number: str


@dataclass(frozen=True, slots=True)
class VisitFixture:
    visit_id: int
    hospital_id: int
    patient_id: int
    doctor_scenario_id: str
    visited_at: datetime
    scenario: str


@dataclass(frozen=True, slots=True)
class Key36FixtureSet:
    hospitals: dict[str, HospitalFixture]
    staff_accounts: dict[str, "Staff"]
    patients: dict[str, PatientFixture]
    visits: dict[str, VisitFixture]
