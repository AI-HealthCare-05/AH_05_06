"""발송 예정 — 와이어프레임 S2-3.

**두 무더기를 한 표에 놓는다.** 앞으로 나갈 것(`SCHEDULED`)과 안 나간
것(`FAILED` · `HELD`)이다. 나누어 두 화면으로 만들지 않는 이유는, 스탭이
묻는 것이 「지금 무엇을 손대야 하나」 하나이기 때문이다 — 원문 캡션이
「앞으로 나갈 것 · 보류는 맨 위에서 이유와 함께」라고 적는다.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator
from tortoise.timezone import now

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


class MessagePatchRequest(BaseModel):
    """예약 문자 시각 변경 또는 예약 취소 요청."""

    model_config = ConfigDict(extra="forbid")

    scheduled_at: datetime | None = None
    status: GuideMessageStatus | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> "MessagePatchRequest":
        has_scheduled_at = self.scheduled_at is not None
        has_status = self.status is not None

        if has_scheduled_at == has_status:
            raise ValueError("scheduled_at 또는 status 중 하나만 입력해야 합니다.")

        if self.status is not None and self.status is not GuideMessageStatus.CANCELED:
            raise ValueError("status는 CANCELED만 요청할 수 있습니다.")

        if self.scheduled_at is not None and self.scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at에는 시간대가 필요합니다.")

        if self.scheduled_at is not None and self.scheduled_at <= now():
            raise ValueError("scheduled_at은 미래 시각이어야 합니다.")

        return self


class MessagePatchResponse(BaseModel):
    """변경된 예약 문자 응답."""

    guide_message_id: int
    scheduled_at: datetime
    status: GuideMessageStatus


class SentMessageItem(BaseModel):
    """발송 이력 한 줄 — 와이어프레임 S2-4.

    **`happened_at` 은 `sent_at` 이 있으면 그것, 없으면 `scheduled_at` 이다.**
    못 나간 줄에는 보낸 시각이 없는데, 원문은 실패 줄에도 시각을 적는다
    (「08-11 10:06 · ⚠ 발송 실패」) — 「언제 일이 있었나」를 묻는 칸이다.
    """

    guide_message_id: int
    visit_id: int
    patient_id: int

    happened_at: datetime
    kind: GuideMessageKind
    status: GuideMessageStatus
    failure_code: GuideMessageFailure | None

    name: str
    hospital_patient_no: str
    gender: PatientGender
    birth_date: date
    age: int
    prescription_set: str | None

    #: **안내문 단위다.** 환자에게 가는 링크가 안내문 하나를 열고, 그 안내문에
    #: 문자가 여럿 달린다 — 어느 문자를 보고 열었는지는 물을 수 없다.
    viewed: bool
    viewed_at: datetime | None


class SentMessageCounts(BaseModel):
    """원문의 칩 넷 — 「전체 210 · ⚠ 실패 1 · 미열람 34 · 열람 175」.

    **열람과 미열람은 나간 것 중에서만 센다.** 못 나간 문자에 열람을 묻는 것은
    뜻이 없다. 원문의 수가 그렇게 맞는다 — 175 + 34 = 209 = 210 − 1.
    """

    total: int
    failed: int
    viewed: int
    unviewed: int


class SentMessageListResponse(BaseModel):
    from_date: date
    to_date: date
    timezone: str = "Asia/Seoul"
    counts: SentMessageCounts
    items: list[SentMessageItem]
    #: 나간 것이 `limit` 를 넘어 잘렸는가. **실패는 잘리지 않는다.**
    #: 원문 요약도 「표에는 일부 행만 표시」라고 적어 둔다.
    truncated: bool
