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


class PatientSort(StrEnum):
    """환자 관리 표(S2-1)를 세우는 기준 — KEY-327.

    **정렬은 서버가 한다.** 화면이 받은 쪽만 다시 세우면 그 쪽 안에서만 맞고,
    쪽을 넘기면 앞 쪽과 겹치거나 빠진다.

    기본은 **등록일 최근순**이다. 전에는 `patient_id` 오름차순이라 방금 등록한
    환자가 맨 뒤 쪽에 있었다 — 등록하고 바로 확인하려면 마지막 쪽까지 넘겨야
    했다.

    `registered_*` 는 **표에 보이는 그 날짜**(`created_at`)로 센다. 보여 주는
    값과 세우는 열쇠가 같아야 한다 — 다르면 「등록 ▼」인데 날짜가 오르락내리락
    해서 화면이 고장난 것처럼 보인다.
    """

    REGISTERED_DESC = "registered_desc"
    REGISTERED_ASC = "registered_asc"
    CHART_ASC = "chart_asc"
    CHART_DESC = "chart_desc"
    VISITED_DESC = "visited_desc"
    VISITED_ASC = "visited_asc"
    #: **이어 보기 전용** — 환자 번호 차례. 등록 화면의 찾기가 쓴다.
    #:
    #: 커서는 `patient_id > cursor` 로 거르므로 세우는 열쇠도 번호여야 한다.
    #: 날짜로 세우면 거르는 열쇠와 갈려, 옛 날짜를 단 나중 번호가 영영 안
    #: 나오거나 이미 본 사람이 다시 나온다. 표에서는 안 쓴다.
    ID_ASC = "id_asc"


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


class RosterPage(BaseModel):
    """쪽 번호로 넘기는 표 — KEY-303.

    커서는 앞으로만 간다. 「이전」과 「3쪽으로」를 하려면 **몇 번째부터 몇 개**가
    필요하다. 기존 `CursorPage` 는 다른 화면이 쓰고 있어 그대로 두고 나란히 둔다.

    `total` 은 **지금 고른 조각의** 총수다. 「전체」의 총수를 주면 조각을 눌렀을
    때 있지도 않은 쪽이 생긴다.
    """

    offset: int
    limit: int
    total: int
    has_next: bool


class PatientListResponse(BaseModel):
    counts: dict[PatientCategory, int]
    selected_category: PatientCategory
    items: list[PatientListItem]
    page: CursorPage
    roster: RosterPage
