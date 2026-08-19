from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalStatus(StrEnum):
    APPROVED = "approved"


class KnowledgeKind(StrEnum):
    APPROVED_GUIDANCE = "approved_guidance"
    APPROVED_KNOWLEDGE = "approved_knowledge"


class Medication(StrictModel):
    name: str
    ingredient: str | None = None
    dosage: str
    purpose: str
    instructions: list[str] = Field(default_factory=list)


class GuidanceSection(StrictModel):
    id: str
    title: str
    body: str
    source_label: str


class ApprovedKnowledge(StrictModel):
    id: str
    title: str
    content: str
    source_label: str
    kind: KnowledgeKind


class ApprovedGuidanceBundle(StrictModel):
    """The only KEY-2 payload accepted by the patient flow.

    Raw document identifiers, locations, OCR text, and draft fields are
    intentionally absent. ``extra='forbid'`` rejects payloads containing them.
    """

    bundle_id: str
    care_episode_id: str
    status: ApprovalStatus
    approved_at: datetime
    clinic_name: str
    encounter_date: date
    patient_display_name: str
    medications: list[Medication]
    medication_guidance: list[GuidanceSection]
    cautions: list[GuidanceSection]
    lifestyle_guidance: list[GuidanceSection]
    knowledge: list[ApprovedKnowledge]
    next_visit_date: date | None = None

    @model_validator(mode="after")
    def require_approved_content(self) -> "ApprovedGuidanceBundle":
        if self.status is not ApprovalStatus.APPROVED:
            raise ValueError("Only approved guidance is accepted")
        if not self.medication_guidance or not self.knowledge:
            raise ValueError("Approved guidance and knowledge are required")
        return self


class ApprovedGuidanceProvider:
    async def get_approved_bundle(self, care_episode_id: str) -> ApprovedGuidanceBundle | None:
        raise NotImplementedError


class InMemoryApprovedGuidanceProvider(ApprovedGuidanceProvider):
    """Local integration adapter. KEY-2 replaces this provider in deployment."""

    def __init__(self) -> None:
        self._bundles: dict[str, ApprovedGuidanceBundle] = {}

    def register(self, bundle: ApprovedGuidanceBundle) -> None:
        self._bundles[bundle.care_episode_id] = bundle

    async def get_approved_bundle(self, care_episode_id: str) -> ApprovedGuidanceBundle | None:
        return self._bundles.get(care_episode_id)
