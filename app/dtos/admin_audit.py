"""어드민 — 감사 로그 조회 (A1-6 · A1-7) 계약. KEY-322.

감사 이벤트는 이미 append-only 로 쌓이고 있는데(KEY-123 · KEY-250 등) **읽을
길이 없었다.** 표가 넷으로 흩어져 있고 통합 `AuditLog` 모델은 없다 — 물리
통합은 별도 논의라, 여기서는 **읽을 때 합친다.**

그래서 이 파일이 하는 일은 「네 표를 한 모양으로 옮기는 계약」을 적는 것이다.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from app.dtos.base import StrictModel


class AuditSource(StrEnum):
    """어느 표에서 왔나. **화면의 「유형」 거르개가 이것을 쓴다.**

    표 이름을 그대로 쓰지 않고 뜻으로 짓는다 — `guide_event` 는 표 이름이지
    사람이 고를 말이 아니다. 표가 합쳐지거나 갈라져도 이 어휘는 산다.
    """

    GUIDE = "guide"
    """안내문 — 생성 · 수정 · 제출 · 승인 · 반려 · 링크 재발급/폐기."""
    OTP = "otp"
    """환자 본인 확인 — 발급 · 발송 실패 · 확인 · 확인 실패 · 잠김."""
    MESSAGE = "message"
    """문자 발송 — 시도 · 발송 · 실패 · 보류."""
    PATIENT_USAGE = "patient_usage"
    """환자가 한 일 — 안내 열람 · 챗봇 답변."""
    STAFF_ACCOUNT = "staff_account"
    """직원 계정 — 추가(KEY-321). 티켓이 적은 넷에는 없던 다섯째다: 계정을
    만드는 것은 **권한을 주는 일**이라, 그것이 빠진 감사 로그는 구멍이다."""
    HOSPITAL = "hospital"
    """의원 정보 — 수정(KEY-331). 여섯째다: 여기 적힌 예약 링크가 **그대로
    문자에 실려 환자에게 나간다.** 언제 어떤 주소가 나갔는지를 되짚으려면
    바뀐 값 자체가 남아야 한다."""


class AuditLogEntry(StrictModel):
    """한 줄. **네 표가 다 이 모양으로 옮겨진다.**

    **원문을 담는 칸이 없다.** 링크 토큰 · OTP 코드 · 환자 이름 · 전화번호 ·
    챗봇 질문 어느 것도 실을 자리가 없다 — 담을 칸을 만들지 않는 것이 담지
    않겠다는 약속을 지키는 가장 확실한 방법이다(`PatientUsageEvent` 가 원문을
    안 담는 것과 같은 규율).

    `summary` 는 **서버가 만든 고정 문구**다. 사용자 입력이 그대로 흘러드는
    자리가 아니다 — `reason` 처럼 사람이 적은 값은 담지 않는다.
    """

    #: 쪽 나눔이 가리키는 자리. `<source>:<그 표의 기본키>` 라 표가 달라도 안 겹친다.
    event_id: str
    occurred_at: datetime
    source: AuditSource
    #: 그 표가 쓰는 유형 값을 그대로 (`APPROVED` · `VERIFIED` · `SENT` …).
    #: 표마다 어휘가 달라서 한 enum 으로 접지 않는다 — 접으면 뜻이 뭉개진다.
    event_type: str
    #: 한 일을 한 직원. **환자가 한 일에는 없다** — 그 자리는 `null` 이다.
    actor_staff_id: int | None
    actor_name: str | None
    #: 어느 진료 건인가. A1-7 이 이 값으로 거른다.
    visit_id: int | None
    #: 사람이 읽을 한 줄. 서버가 짓는다.
    summary: str


class AuditLogPage(StrictModel):
    entries: list[AuditLogEntry]
    #: 다음 쪽 열쇠. 더 없으면 `null`.
    next_cursor: str | None
    has_more: bool


class AuditLogQuery(StrictModel):
    """거르개. **모두 선택**이고, 아무것도 안 주면 의원 전체를 최근순으로 준다."""

    #: 이 시각 **이후**(포함). 날짜만 주면 그날 0시로 읽힌다.
    occurred_from: datetime | None = None
    #: 이 시각 **이전**(포함).
    occurred_to: datetime | None = None
    #: 그 직원이 한 일만. 환자가 한 일은 행위자가 없어 이 거르개에 안 걸린다.
    actor_staff_id: int | None = None
    source: AuditSource | None = None
    #: A1-7 — 이 진료 건의 **모든 유형**을 시간순으로.
    visit_id: int | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: str | None = None
