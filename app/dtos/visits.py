from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.dtos.base import BaseSerializerModel, CursorPage
from app.models.ocr import OcrDocumentType
from app.models.visits import GuideSectionKey, VisitCheckKey, VisitStatus


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


class CheckAnswer(BaseModel):
    """확인 항목 하나의 답 — 와이어프레임 S1-6.

    `checked` 가 `null` 이면 **아직 안 여쭌 것**이다. `false` 는 여쭤서 아니라고
    한 것이다. 하나로 뭉치면 안내문이 「우울증 병력 없음」을 확인한 것처럼 적을
    수 있는데, 실제로는 아무도 안 물었을 수 있다 — 안전에 걸리는 항목이라 이
    구별이 필요하다.
    """

    item_key: VisitCheckKey
    checked: bool | None = None


class CheckAnswerSaveRequest(BaseModel):
    """확인 항목 저장 — **한 판을 통째로** 받는다.

    항목 하나씩 받으면 중간에 끊겼을 때 「우울증은 답했는데 당뇨는 안 답한」
    반쪽 상태가 남고, 화면은 그것을 「안 여쭌 것」과 구별하지 못한다.
    """

    answers: list[CheckAnswer]


class CheckAnswerResponse(BaseModel):
    visit_id: int
    #: 물어볼 항목 전부. 아직 안 여쭌 것은 `checked` 가 `null` 이다.
    answers: list[CheckAnswer]


class TimelineCategory(StrEnum):
    """진료 한 건의 이력을 큰 갈래로 나눈다 — 화면이 갈래별로 묶어 보여 준다.

    `SEND`(문자 발송)는 아직 없다. `SendLog` 계열 모델이 Sprint 5 범위라
    발송 시각·상태를 남기는 자리가 없다(`docs/구현현황.md` D1-5·D1-6). 값을 미리
    넣어 두면 화면이 「곧 온다」로 오해하므로, 발송 이력이 생기는 일감에서 함께
    추가한다.
    """

    #: 진료가 열린 것. 다른 표가 아니라 `visit` 자신이 갖고 있다.
    VISIT = "VISIT"
    DOCUMENT = "DOCUMENT"
    OCR = "OCR"
    GUIDE = "GUIDE"
    CHECK_IN = "CHECK_IN"
    #: **환자가 한 일.** 직원이 한 일과 축이 다르다 — 화면이 「환자」로 적는다.
    PATIENT = "PATIENT"


class TimelineEvent(StrEnum):
    """세부 사건 이름 — **어휘를 여기서 못 박는다.**

    각 값은 이미 다른 표가 남긴 사실 하나에 그대로 대응한다. `medical_document`
    한 행이 `DOCUMENT_UPLOADED`, `ocr_job.status` 가 `OCR_COMPLETED`/`OCR_FAILED`,
    `ocr_result.confirmed_at` 이 `OCR_CONFIRMED`, `guide_event.event_type` 넷이
    `GUIDE_*`, `check_in` 한 행이 `CHECK_IN_SUBMITTED` 다. 새 사건을 늘리려면
    그 사건을 남기는 표부터 있어야 한다.
    """

    VISIT_CREATED = "VISIT_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    OCR_STARTED = "OCR_STARTED"
    OCR_COMPLETED = "OCR_COMPLETED"
    OCR_FAILED = "OCR_FAILED"
    OCR_CONFIRMED = "OCR_CONFIRMED"
    GUIDE_GENERATED = "GUIDE_GENERATED"
    GUIDE_EDITED = "GUIDE_EDITED"
    #: 스탭이 확인을 마치고 의사에게 넘겼다 (와이어프레임 S1-11).
    GUIDE_SUBMITTED = "GUIDE_SUBMITTED"
    GUIDE_APPROVED = "GUIDE_APPROVED"
    #: 승인을 거뒀다. 승인 줄을 지우지 않고 이 줄을 더한다 — 지우면
    #: 「왜 예약이 사라졌지」에 답할 수 없다.
    GUIDE_UNAPPROVED = "GUIDE_UNAPPROVED"
    #: 초안을 다시 만들었다 (KEY-273). 옛 생성 줄을 지우지 않고 이 줄을 더한다.
    GUIDE_REGENERATED = "GUIDE_REGENERATED"
    GUIDE_RETURNED = "GUIDE_RETURNED"
    CHECK_IN_SUBMITTED = "CHECK_IN_SUBMITTED"
    #: 환자가 안내문을 열었다. `section_key` 가 있으면 그 장까지 읽은 것이다.
    GUIDE_VIEWED = "GUIDE_VIEWED"
    #: 환자가 챗봇에 묻고 답을 받았다.
    CHATBOT_ANSWERED = "CHATBOT_ANSWERED"


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
    #: 사람 이름. 화면이 그대로 적는다 — 번호만 주면 화면이 다시 물어야 하고,
    #: D1-6 은 「누가 언제」를 한 줄로 보여 준다. 환자가 한 일이나 시스템
    #: 사건이면 비어 있다. **모르는 사람은 지어내지 않는다** — 지워진 계정일
    #: 수 있고, 그때는 화면이 「알 수 없음」이라 적는다.
    actor: str | None = None
    #: `GUIDE_EDITED` 면 어느 갈래를 고쳤나.
    section_key: GuideSectionKey | None = None
    #: `DOCUMENT_*` 면 어떤 문서였나.
    document_type: OcrDocumentType | None = None
    #: 스탭에게 보이는 짧은 부연 — 반려 사유, OCR 실패 코드 등. 환자 대화·검사값
    #: 원문은 담지 않는다.
    note: str | None = None


class ScheduledMessage(BaseModel):
    """환자에게 나갈 문자 한 통 — 와이어프레임 D1-6 「발송 · 예정」.

    **한 통이 한 줄이다.** 다섯 통 중 어느 것이든 실패할 수 있고, 실패한
    것만 고쳐 다시 보낸다.

    이력(`entries`)과 **따로 둔다.** 이력은 이미 일어난 일이고 이것은 앞으로
    일어날 일이라, 한 줄로 섞으면 「보냈다」와 「보낼 것이다」가 같아 보인다.
    """

    #: GUIDE · CHECK_D7 · CHECK_D15 · CHECK_D30 · RUN_OUT.
    kind: str
    #: SCHEDULED · SENT · FAILED · HELD · CANCELED
    status: str
    at: datetime
    sent_at: datetime | None = None
    #: 못 나간 이유 — 넷뿐이다(D1-7).
    failure_code: str | None = None
    #: 왜 붙들고 있나 — 둘뿐이다(S2-3). `status` 가 `HELD` 일 때만 찬다.
    #: 실패 사유와 **다른 목록**이다 — 재는 것이 다르다.
    hold_reason: str | None = None


class VisitTimelineResponse(BaseModel):
    visit_id: int
    #: 오래된 사건이 먼저다 — 「문서 올림 → 판독 → 생성 → 승인」을 읽는 차례.
    entries: list[VisitTimelineEntry]
    #: 나갈 문자들. 승인 전에는 비어 있다 — 예약은 승인이 만든다.
    messages: list[ScheduledMessage] = []
    #: 안내문이 몇 장인가 — **분모를 서버가 준다.**
    #:
    #: 화면이 제 목록으로 세면 장이 늘 때 서버와 갈린다. 실제로 S2-2 는
    #: 서버 값을 쓰고 D1-6 은 제 사본을 써서 같은 환자를 다르게 셀 수
    #: 있었다 (`#189` 리뷰, 2heej).
    guide_pages_total: int = 0
