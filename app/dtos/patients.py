from datetime import date, datetime
from enum import StrEnum
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.utils.common import normalize_phone_number
from app.dtos.base import BaseSerializerModel
from app.models.patients import PatientGender

SEOUL = ZoneInfo("Asia/Seoul")


class PatientCategory(StrEnum):
    ALL = "ALL"
    IN_TREATMENT = "IN_TREATMENT"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    SMS_OPT_OUT = "SMS_OPT_OUT"
    INACTIVE_6_MONTHS = "INACTIVE_6_MONTHS"


def calculate_age(birth_date: date, *, as_of: date | None = None) -> int:
    reference = as_of or datetime.now(SEOUL).date()
    return reference.year - birth_date.year - ((reference.month, reference.day) < (birth_date.month, birth_date.day))


class PatientCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hospital_patient_no: Annotated[str, Field(min_length=1, max_length=50)]
    name: Annotated[str, Field(min_length=1, max_length=50)]
    birth_date: date
    gender: PatientGender = PatientGender.UNKNOWN
    phone: Annotated[str, Field(min_length=10, max_length=20)]
    sms_consent: bool

    @field_validator("hospital_patient_no", "name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = normalize_phone_number(value)
        if not 10 <= len(normalized) <= 11:
            raise ValueError("phone must contain 10 or 11 digits")
        return normalized


class PatientUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=50)]
    birth_date: date | None = None
    gender: PatientGender | None = None
    phone: Annotated[str | None, Field(default=None, min_length=10, max_length=20)]
    sms_consent: bool | None = None
    hospital_patient_no: Annotated[str | None, Field(default=None, min_length=1, max_length=50)]
    correction_reason: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]

    @field_validator("name", "hospital_patient_no", "correction_reason")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("phone")
    @classmethod
    def normalize_optional_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_phone_number(value)
        if not 10 <= len(normalized) <= 11:
            raise ValueError("phone must contain 10 or 11 digits")
        return normalized

    @model_validator(mode="after")
    def validate_chart_number_correction(self) -> "PatientUpdateRequest":
        if (self.hospital_patient_no is None) != (self.correction_reason is None):
            raise ValueError("hospital_patient_no and correction_reason must be provided together")
        return self


class LatestVisitResponse(BaseSerializerModel):
    visit_id: int
    visited_at: datetime
    status: str


class PatientResponse(BaseSerializerModel):
    patient_id: int
    hospital_patient_no: str
    name: str
    birth_date: date
    gender: PatientGender
    phone: str
    sms_consent: bool
    sms_consented_at: datetime | None
    sms_opted_out_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    def age(self) -> int:
        return calculate_age(self.birth_date)


class PatientListItem(PatientResponse):
    latest_visit: LatestVisitResponse | None = None


class CursorPage(BaseModel):
    next_cursor: str | None
    has_next: bool


class PatientListResponse(BaseModel):
    counts: dict[PatientCategory, int]
    selected_category: PatientCategory
    items: list[PatientListItem]
    page: CursorPage
