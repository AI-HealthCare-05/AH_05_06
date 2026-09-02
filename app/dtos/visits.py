from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.dtos.base import BaseSerializerModel, CursorPage
from app.models.visits import VisitCheckKey, VisitStatus


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
