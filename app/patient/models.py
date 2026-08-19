from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from app.patient.contracts import ApprovedGuidanceBundle


class LinkState(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AccessPurpose(StrEnum):
    GUIDANCE = "guidance"
    FOLLOW_UP = "follow_up"


class AdherenceStatus(StrEnum):
    TAKING = "taking"
    UNCOMFORTABLE = "uncomfortable"
    SOMETIMES_MISSED = "sometimes_missed"
    STOPPED_SIDE_EFFECTS = "stopped_side_effects"
    STOPPED_BETTER = "stopped_better"


class PainType(StrEnum):
    DYSMENORRHEA = "dysmenorrhea"
    DYSPAREUNIA = "dyspareunia"
    DYSCHEZIA = "dyschezia"
    CHRONIC_PELVIC = "chronic_pelvic"


@dataclass
class PatientLink:
    id: str
    care_episode_id: str
    purpose: AccessPurpose
    bundle: ApprovedGuidanceBundle
    token_digest: str
    phone_ciphertext: str
    phone_last4: str
    birth_date_digest: str
    encounter_date: date
    created_at: datetime
    send_at: datetime
    expires_at: datetime
    state: LinkState
    sent_at: datetime | None = None
    revoked_at: datetime | None = None
    resend_dates: list[date] = field(default_factory=list)
    fallback_failures: int = 0
    fallback_locked_until: datetime | None = None


@dataclass
class OtpChallenge:
    id: str
    link_id: str
    code_digest: str
    created_at: datetime
    expires_at: datetime
    resend_count: int = 0
    failures: int = 0
    locked_at: datetime | None = None
    verified_at: datetime | None = None


@dataclass
class PatientSession:
    id: str
    link_id: str
    token_digest: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass
class PendingDelivery:
    link_id: str
    token_ciphertext: str


@dataclass
class FollowUpResponse:
    id: str
    link_id: str
    adherence: AdherenceStatus
    has_pain: bool
    pain_score: int | None
    pain_types: tuple[PainType, ...]
    memo: str | None
    created_at: datetime
