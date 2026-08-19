from datetime import date, datetime

from pydantic import BaseModel, Field

from app.patient.contracts import GuidanceSection, Medication
from app.patient.models import AccessPurpose, AdherenceStatus, LinkState, PainType


class IssueLinkRequest(BaseModel):
    care_episode_id: str = Field(min_length=1, max_length=100)
    phone_number: str
    birth_date: date
    send_at: datetime | None = None
    purpose: AccessPurpose = AccessPurpose.GUIDANCE


class LinkManagementResponse(BaseModel):
    id: str
    state: LinkState
    send_at: datetime
    expires_at: datetime


class LinkTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class LinkInspectionResponse(BaseModel):
    masked_phone: str
    encounter_date: date
    expires_at: datetime
    purpose: AccessPurpose


class OtpRequestedResponse(BaseModel):
    challenge_id: str
    expires_at: datetime
    masked_phone: str


class VerifyOtpRequest(BaseModel):
    challenge_id: str
    code: str = Field(pattern=r"^\d{6}$")


class ReissueLinkRequest(LinkTokenRequest):
    phone_number: str
    birth_date: date


class GuidanceResponse(BaseModel):
    clinic_name: str
    encounter_date: date
    patient_display_name: str
    medications: list[Medication]
    medication_guidance: list[GuidanceSection]
    cautions: list[GuidanceSection]
    lifestyle_guidance: list[GuidanceSection]
    next_visit_date: date | None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class FollowUpSubmitRequest(BaseModel):
    adherence: AdherenceStatus
    has_pain: bool
    pain_score: int | None = Field(default=None, ge=0, le=10)
    pain_types: tuple[PainType, ...] = ()
    memo: str | None = Field(default=None, max_length=500)


class FollowUpResponseSchema(BaseModel):
    id: str
    adherence: AdherenceStatus
    has_pain: bool
    pain_score: int | None
    pain_types: tuple[PainType, ...]
    memo: str | None
    created_at: datetime
