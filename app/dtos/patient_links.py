"""개발용 환자 링크 계약 — KEY-90 (8/27 Walking Skeleton)."""

from datetime import datetime
from typing import Literal

from app.dtos.base import StrictModel
from app.models.visits import GuideSectionKey


class PatientLinkIssueResponse(StrictModel):
    path: str
    expires_at: datetime
    demo_only: Literal[True] = True


class PatientGuideSectionResponse(StrictModel):
    key: GuideSectionKey
    body: str


class PatientGuideResponse(StrictModel):
    version: int
    approved_at: datetime
    expires_at: datetime
    sections: list[PatientGuideSectionResponse]
    demo_only: Literal[True] = True
