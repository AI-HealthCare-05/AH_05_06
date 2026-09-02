from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.time import DISPLAY_TIMEZONE
from app.core.utils.common import normalize_phone_number
from app.dtos.base import BaseSerializerModel, CursorPage
from app.dtos.visits import DoctorResponse
from app.models.patients import PatientGender
from app.services.work_category import DetailStatus, WorkCategory


class PatientCategory(StrEnum):
    ALL = "ALL"
    IN_TREATMENT = "IN_TREATMENT"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    SMS_OPT_OUT = "SMS_OPT_OUT"
    INACTIVE_6_MONTHS = "INACTIVE_6_MONTHS"


def calculate_age(birth_date: date, *, as_of: date | None = None) -> int:
    reference = as_of or datetime.now(DISPLAY_TIMEZONE).date()
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
    """환자 관리 표 한 줄 — 와이어프레임 S2-1.

    **목록(S1 · D1)이 칩으로 보이던 것을 여기서는 열로 보인다.** 원문 주석이
    그렇게 적는다 — 「같은 속성, 표기만 서식에 맞춘다」. 그래서 새 이름을 짓지
    않고 접수대 목록과 **같은 값**(`WorkCategory` · `DetailStatus`)을 싣는다.
    두 화면이 같은 환자를 다르게 부르면 어느 쪽이 맞는지 알 수 없다.
    """

    latest_visit: LatestVisitResponse | None = None
    #: 최근 진료의 진단명. 판독에서 확정된 것만 온다 — 없으면 비어 있다.
    diagnosis_name: str | None = None
    doctor: DoctorResponse | None = None
    #: 기본 상태 — 목록 상단 탭과 같은 대분류 다섯
    work_category: WorkCategory | None = None
    #: 세부 상태 — 「무엇 때문에」
    detail_status: DetailStatus | None = None
    #: 이탈 배지. **빈 목록이 정상이다** — 챙길 일이 없다는 뜻이다.
    flags: list[str] = Field(default_factory=list)


class PatientListResponse(BaseModel):
    counts: dict[PatientCategory, int]
    selected_category: PatientCategory
    items: list[PatientListItem]
    page: CursorPage
