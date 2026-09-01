"""발송 예정 — 와이어프레임 S2-3.

**두 무더기를 한 표에 놓는다.** 앞으로 나갈 것(`SCHEDULED`)과 안 나간
것(`FAILED` · `HELD`)이다. 나누어 두 화면으로 만들지 않는 이유는, 스탭이
묻는 것이 「지금 무엇을 손대야 하나」 하나이기 때문이다 — 원문 캡션이
「앞으로 나갈 것 · 보류는 맨 위에서 이유와 함께」라고 적는다.
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.models.patients import PatientGender
from app.models.visits import (
    GuideMessageFailure,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
)


class ScheduledMessageItem(BaseModel):
    """표 한 줄 — 예정 시각 · 환자 · 식별정보 · 세트명 · 종류 · 상태."""

    guide_message_id: int
    visit_id: int
    patient_id: int

    scheduled_at: datetime
    kind: GuideMessageKind
    status: GuideMessageStatus
    #: 보류일 때만 찬다. 실패 사유와 **목록이 다르다** — 재는 것이 다르다.
    hold_reason: GuideMessageHold | None
    #: 실패일 때만 찬다.
    failure_code: GuideMessageFailure | None

    name: str
    hospital_patient_no: str
    gender: PatientGender
    birth_date: date
    age: int
    #: 진료 당시 처방 세트 이름의 스냅샷. 처방이 없으면 비어 있다.
    prescription_set: str | None


class ScheduledMessageCounts(BaseModel):
    """화면 위의 칩과 아래 요약 줄이 같은 값을 쓰게 한다.

    **`total` 과 `window` 는 세는 범위가 다르다.** 위는 창과 무관한 전부이고
    아래는 고른 기간 안의 예정이다 — 원문의 「전체 42」와 「이번 주 18」이
    그 둘이다. 한 이름으로 뭉치면 화면이 42 를 「이번 주」라고 말하게 된다.
    """

    total: int
    failed: int
    held: int
    today: int
    window: int


class ScheduledMessageListResponse(BaseModel):
    days: int
    timezone: str = "Asia/Seoul"
    counts: ScheduledMessageCounts
    items: list[ScheduledMessageItem]
    #: 예정이 `limit` 를 넘어 잘렸는가. **안 나간 것은 잘리지 않는다** —
    #: 이 화면의 요점이 그것이라, 잘라 놓고 조용히 있으면 안 된다.
    truncated: bool
