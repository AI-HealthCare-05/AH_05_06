from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.dtos.base import BaseSerializerModel
from app.dtos.patients import CursorPage
from app.models.ocr import OcrDocumentType
from app.models.visits import GuideSectionKey, VisitStatus


class VisitCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: int | None = None
    department_id: int | None = None
    visited_at: datetime
    visit_summary: str | None = None
    doctor_note: str | None = None
    status: VisitStatus = VisitStatus.COMPLETED
    planned_stop: bool = False


class VisitUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: int | None = None
    department_id: int | None = None
    visited_at: datetime | None = None
    visit_summary: Annotated[str | None, Field(default=None, max_length=10000)]
    doctor_note: Annotated[str | None, Field(default=None, max_length=10000)]
    status: VisitStatus | None = None
    planned_stop: bool | None = None


class DoctorResponse(BaseModel):
    doctor_id: int
    name: str


class VisitResponse(BaseSerializerModel):
    visit_id: int
    patient_id: int
    doctor_id: int | None
    doctor: DoctorResponse | None = None
    department: str | None
    visited_at: datetime
    visit_summary: str | None
    doctor_note: str | None
    status: VisitStatus
    planned_stop: bool
    created_at: datetime
    updated_at: datetime


class VisitListResponse(BaseModel):
    items: list[VisitResponse]
    page: CursorPage


class TimelineCategory(StrEnum):
    """진료 한 건의 이력을 큰 갈래로 나눈다 — 화면이 갈래별로 묶어 보여 준다.

    `SEND`(문자 발송)는 아직 없다. `SendLog` 계열 모델이 Sprint 5 범위라
    발송 시각·상태를 남기는 자리가 없다(`docs/구현현황.md` D1-5·D1-6). 값을 미리
    넣어 두면 화면이 「곧 온다」로 오해하므로, 발송 이력이 생기는 일감에서 함께
    추가한다.
    """

    DOCUMENT = "DOCUMENT"
    OCR = "OCR"
    GUIDE = "GUIDE"
    CHECK_IN = "CHECK_IN"


class TimelineEvent(StrEnum):
    """세부 사건 이름 — **어휘를 여기서 못 박는다.**

    각 값은 이미 다른 표가 남긴 사실 하나에 그대로 대응한다. `medical_document`
    한 행이 `DOCUMENT_UPLOADED`, `ocr_job.status` 가 `OCR_COMPLETED`/`OCR_FAILED`,
    `ocr_result.confirmed_at` 이 `OCR_CONFIRMED`, `guide_event.event_type` 넷이
    `GUIDE_*`, `check_in` 한 행이 `CHECK_IN_SUBMITTED` 다. 새 사건을 늘리려면
    그 사건을 남기는 표부터 있어야 한다.
    """

    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    OCR_STARTED = "OCR_STARTED"
    OCR_COMPLETED = "OCR_COMPLETED"
    OCR_FAILED = "OCR_FAILED"
    OCR_CONFIRMED = "OCR_CONFIRMED"
    GUIDE_GENERATED = "GUIDE_GENERATED"
    GUIDE_EDITED = "GUIDE_EDITED"
    GUIDE_APPROVED = "GUIDE_APPROVED"
    GUIDE_RETURNED = "GUIDE_RETURNED"
    CHECK_IN_SUBMITTED = "CHECK_IN_SUBMITTED"


class VisitTimelineEntry(BaseModel):
    """이미 다른 표에 남아 있는 사건 하나를 화면이 읽을 모양으로 옮긴 것.

    이 API 는 사건을 **만들지 않는다** — `medical_document`·`ocr_job`·
    `ocr_result`·`guide_event`·`check_in` 이 각자 남긴 것을 시간순으로 모을 뿐이다.
    """

    at: datetime
    category: TimelineCategory
    event: TimelineEvent
    #: 이 사건을 일으킨 직원. 환자 스스로 한 일(체크인)이나 시스템 사건이면 비어 있다.
    actor_id: int | None = None
    #: `GUIDE_EDITED` 면 어느 갈래를 고쳤나.
    section_key: GuideSectionKey | None = None
    #: `DOCUMENT_*` 면 어떤 문서였나.
    document_type: OcrDocumentType | None = None
    #: 스탭에게 보이는 짧은 부연 — 반려 사유, OCR 실패 코드 등. 환자 대화·검사값
    #: 원문은 담지 않는다.
    note: str | None = None


class VisitTimelineResponse(BaseModel):
    visit_id: int
    #: 오래된 사건이 먼저다 — 「문서 올림 → 판독 → 생성 → 승인」을 읽는 차례.
    entries: list[VisitTimelineEntry]
