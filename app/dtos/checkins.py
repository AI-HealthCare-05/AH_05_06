"""D+7 복약·통증 응답 계약 — KEY-151 최소 범위."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.dtos.base import StrictModel
from app.models.visits import CheckInMedication

PainType = Literal["menstrual", "intercourse", "defecation", "chronic_pelvic"]


class CheckInPainRequest(StrictModel):
    had: bool
    score: int | None = Field(default=None, ge=0, le=10)
    types: list[PainType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pain_details(self) -> "CheckInPainRequest":
        if self.had and self.score is None:
            raise ValueError("통증이 있으면 0~10 점수를 입력해야 합니다.")
        if not self.had and (self.score is not None or self.types):
            raise ValueError("통증이 없으면 점수와 유형을 입력할 수 없습니다.")
        if len(self.types) != len(set(self.types)):
            raise ValueError("통증 유형은 중복할 수 없습니다.")
        return self


class CheckInCreateRequest(StrictModel):
    medication: CheckInMedication
    pain: CheckInPainRequest | None = None
    note: str | None = Field(default=None, max_length=1000)
    client_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    client_session_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    client_sequence: int | None = Field(default=None, ge=1, le=9007199254740991, strict=True)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def complete_stamp(self) -> "CheckInCreateRequest":
        supplied = (self.client_id, self.client_session_id, self.client_sequence)
        if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
            raise ValueError("신호 식별자는 세 필드를 함께 보내야 합니다.")
        return self


class CheckInSignalRequest(StrictModel):
    answer_key: CheckInMedication
    client_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    client_session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    client_sequence: int = Field(ge=1, le=9007199254740991, strict=True)


class CheckInSignalResponse(StrictModel):
    signal_id: int
    answer_key: CheckInMedication
    notify: bool
    current: bool
    current_answer_key: CheckInMedication


class HospitalSignalResponse(StrictModel):
    state_id: int
    signal_id: int | None
    answer_key: CheckInMedication
    needs_review: bool
    status: Literal["OPEN", "ACKNOWLEDGED", "NOT_REQUIRED"]
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_state(cls, state) -> "HospitalSignalResponse":
        return cls(
            state_id=state.state_id,
            signal_id=state.signal_id,
            answer_key=state.answer_key,
            needs_review=state.needs_review,
            status="NOT_REQUIRED" if not state.needs_review else ("ACKNOWLEDGED" if state.acknowledged_at else "OPEN"),
            acknowledged_by=state.acknowledged_by,
            acknowledged_at=state.acknowledged_at,
            updated_at=state.updated_at,
        )


class SignalAcknowledgeRequest(StrictModel):
    signal_id: int | None
    updated_at: datetime


class CheckInAnswerContent(StrictModel):
    lead: str
    body: str | None = None
    ask: bool = False
    notify: bool = False


class CheckInPainTypeResponse(StrictModel):
    key: PainType
    label: str


class CheckInReadResponse(StrictModel):
    round_label: Literal["복약 7일째 · 첫 확인"] = "복약 7일째 · 첫 확인"
    drug_name: None = None
    answers: dict[CheckInMedication, CheckInAnswerContent | None]
    pain_types: list[CheckInPainTypeResponse]
    next_checkin: str | None = None
    next_visit: str | None = None
    answered: bool
    demo_only: Literal[True] = True


class CheckInPainResponse(StrictModel):
    had: bool
    score: int | None
    types: list[PainType]


class CheckInSaveResponse(StrictModel):
    check_in_id: int
    saved: Literal[True] = True
    medication: CheckInMedication
    pain: CheckInPainResponse | None
    note: str | None = None
    signal_answer_key: CheckInMedication | None = None
    guide_url: None = None
    next_checkin: str | None = None
    next_visit: str | None = None
    demo_only: Literal[True] = True


class HospitalCheckInResponse(StrictModel):
    check_in_id: int
    visit_id: int
    medication: CheckInMedication
    pain: CheckInPainResponse | None
    note: str | None = None
    submitted_at: datetime
    demo_only: Literal[True] = True
