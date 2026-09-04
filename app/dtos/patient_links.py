"""환자 링크·P2~P5 공개 응답 계약 — KEY-90, KEY-241."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.dtos.base import StrictModel
from app.models.visits import GuideSectionKey


class GuidePageViewRequest(StrictModel):
    """환자가 연 장 하나 — KEY-256.

    **칸이 하나뿐이다.** 언제 열었는지는 서버가 찍고, 누가 열었는지는 토큰이
    말한다. 화면이 시각을 보내면 브라우저 시계를 믿는 셈이 되고, 이 저장소는
    그 부류로 이미 크게 데었다(저장 시각이 아홉 시간 어긋나 링크 만료 비교가
    깨져 있었다).
    """

    section: GuideSectionKey


class PatientLinkIssueResponse(StrictModel):
    path: str
    expires_at: datetime
    demo_only: Literal[True] = True


class PatientGuideSectionResponse(StrictModel):
    key: GuideSectionKey
    body: str


class PatientMedicationStatResponse(StrictModel):
    drug_name: str = Field(serialization_alias="drugName")
    drug_sub: str | None = Field(default=None, serialization_alias="drugSub")
    prescribed: int = Field(ge=0)
    day_on: int | None = Field(default=None, serialization_alias="dayOn")
    remaining: int | None = None
    pct: int | None = Field(default=None, ge=0, le=100)
    out: str | None = None
    why: str | None = None


class PatientGuideGoalResponse(StrictModel):
    n: str
    a: str | None = None
    now: str | None = None
    t: str | None = None
    has_chart: bool = Field(default=False, serialization_alias="hasChart")
    range_label: str | None = Field(default=None, serialization_alias="rangeLabel")


class PatientGuideDrugResponse(StrictModel):
    n: str
    s: str | None = None
    d: str | None = None


class PatientGuideDetailResponse(StrictModel):
    summary: str | None = None
    goals: list[PatientGuideGoalResponse] = Field(default_factory=list)
    goal_say: str | None = Field(default=None, serialization_alias="goalSay")
    drug: PatientGuideDrugResponse | None = None
    why: list[str] = Field(default_factory=list)
    how: str | None = None
    next: str | None = None


class PatientCareBlockResponse(StrictModel):
    t: str | None = None
    p: list[str] = Field(default_factory=list)


class PatientCareResponse(StrictModel):
    title: str | None = None
    blocks: list[PatientCareBlockResponse] = Field(default_factory=list)
    danger: list[str] = Field(default_factory=list)
    ask: str | None = None


class PatientLifeAxisResponse(StrictModel):
    chal: str | None = None
    goal: str | None = None
    title: str | None = None
    p: list[str] = Field(default_factory=list)


class PatientLifeResponse(StrictModel):
    sub: str | None = None
    challenges: list[list[str]] = Field(default_factory=list)
    axes: dict[str, PatientLifeAxisResponse] = Field(default_factory=dict)


class PatientChatResponse(StrictModel):
    chips: list[str] = Field(default_factory=list)


class PatientGuideResponse(StrictModel):
    version: int
    approved_at: datetime
    expires_at: datetime
    sections: list[PatientGuideSectionResponse]
    visit: str | None = None
    clinic: str | None = None
    # OTP 인증한 뷰어에게만 전체 이름을 채운다. 인증 전에는 생략한다 — KEY-268 / KEY-94.
    patient_name: str | None = None
    disease: str | None = None
    stat: PatientMedicationStatResponse | None = None
    guide: PatientGuideDetailResponse | None = None
    care: PatientCareResponse | None = None
    life: PatientLifeResponse | None = None
    chat: PatientChatResponse | None = None
    demo_only: Literal[True] = True
