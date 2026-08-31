"""진료 처리 이력 — KEY-234, 와이어프레임 D1-6.

승인 뒤에 무슨 일이 있었는지 볼 자리가 없었다 — 보냈는지 · 열었는지 ·
답했는지가 어디에도 안 보였다.

**시스템이 한 일도 숨기지 않는다.** 사람이 한 것만 보면 절반이 빈다
(D1-6 캡션). 다만 「누가 이 환자를 열어봤나」는 여기 넣지 않는다 — 그건
관리 영역(어드민 A1-7)이다.
"""

from datetime import datetime

from app.dtos.base import StrictModel


class TimelineEntry(StrictModel):
    #: 언제. 화면이 시각만 떼어 쓴다(「10:32」).
    at: datetime
    #: 무엇을 한 것인가 — 화면이 사람 말로 옮긴다. 서버는 코드를 준다.
    kind: str
    #: 누가. 사람이면 이름, 시스템이 한 것이면 None 이다 —
    #: 화면이 「시스템」으로 적는다. 빈 문자열로 두면 이름이 없는 사람과 섞인다.
    actor: str | None = None
    #: 어느 항목에 대한 것인가(수정 · 열람). 없을 수 있다.
    section: str | None = None
    #: 되돌린 사유처럼 그 줄에만 붙는 한 줄. 없을 수 있다.
    detail: str | None = None


class ScheduledMessage(StrictModel):
    """환자에게 나갈 문자 한 통 — 와이어프레임 D1-6 「발송 · 예정」.

    **한 통이 한 줄이다.** 다섯 통 중 어느 것이든 실패할 수 있고, 실패한
    것만 고쳐 다시 보낸다.
    """

    #: 무엇인가 — GUIDE · CHECK_D7 · CHECK_D15 · CHECK_D30 · RUN_OUT.
    #: 화면이 사람 말로 옮긴다.
    kind: str
    #: 지금 어디에 있나 — SCHEDULED · SENT · FAILED · CANCELED
    status: str
    at: datetime
    sent_at: datetime | None = None
    #: 못 나간 이유. 화면이 사람 말로 옮긴다 — 코드를 그대로 보여 주지 않는다.
    failure_code: str | None = None


class TimelineResponse(StrictModel):
    visit_id: int
    #: **오래된 것이 위다.** 진료가 어떻게 흘러갔는지 읽는 자리라
    #: 최신순으로 뒤집으면 거꾸로 읽게 된다.
    entries: list[TimelineEntry]
    #: 나갈 문자들. 승인 전에는 비어 있다 — 예약은 승인이 만든다.
    messages: list[ScheduledMessage] = []
