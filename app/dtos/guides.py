"""안내문 응답 모양 — KEY-111.

**화면이 이미 쓰고 있는 이름을 그대로 쓴다.** `#48`(KEY-86)의
`frontend/js/doctor-api.js` 가 목업으로 이 모양을 쓰고 있어서, 여기서
이름을 바꾸면 화면을 다시 고쳐야 한다. 계약을 먼저 적어 두고 양쪽이
같은 것을 보는 것이 이 파일의 목적이다.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.patients import PatientGender
from app.models.visits import GuideMessageKind, GuideSectionKey, GuideStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionResponse(StrictModel):
    key: GuideSectionKey
    body: str
    #: 사람이 고쳤는지. 화면이 「수정됨」을 붙이는 근거다.
    edited: bool
    #: 🚨 응급 문장이면 참. 화면이 [수정] 버튼을 없앤다.
    locked: bool
    #: ⚠ 문구. **서버가 판정한다** — 「AI 가 자신 없는 곳」을 화면이 알 수 없다.
    warn: str | None = None


class PatientHead(StrictModel):
    """승인 화면 머리에 서는 환자. **누구의 안내문인지**를 말한다.

    이것이 없으면 원장님은 화면에 이름 없이 뜬 본문을 승인하게 된다. 승인은
    곧 그 환자에게 발송이라, 누구인지 모르고 누르는 자리를 만들면 안 된다.

    `birth_date` 와 `age` 를 **함께** 준다 — 계약 §4 가 「동명이인 확인과 계산
    근거를 위해 두 값을 함께 제공한다」로 정해 둔 그대로다. `age` 는 저장값이
    아니라 조회 시점의 현지 날짜로 계산한 읽기 전용 값이다.

    `phone` 은 넣지 않는다. 이 화면은 「누구인지」만 알면 되고, 발송 번호는
    서버가 안다. 응답에 실으면 승인할 때마다 전화번호가 화면과 로그를 지난다.
    """

    name: str
    birth_date: date
    age: int
    gender: PatientGender
    hospital_patient_no: str


class GuideResponse(StrictModel):
    visit_id: int
    #: 이 안내문이 누구 것인가. 화면 머리가 이 값으로 산다.
    patient: PatientHead
    #: 진료 한 줄 요약(`visit.visit_summary`). 없을 수 있다.
    summary: str | None = None
    status: GuideStatus
    version: int
    sections: list[SectionResponse]
    approved_at: datetime | None = None
    scheduled_at: datetime | None = None
    returned_reason: str | None = None


class SectionEditRequest(StrictModel):
    body: str = Field(min_length=1, max_length=20000)


class ReturnRequest(StrictModel):
    #: 비어 있으면 되돌리지 않는다 — 이 문장이 스탭 알림에 그대로 뜬다.
    reason: str = Field(min_length=1, max_length=200)


class MessageRound(StrictModel):
    """문자 회차 하나 — 와이어프레임 S1-14.

    `body` 가 `null` 이면 **기본 문구**다. 빈 문자열도 같은 뜻으로 받는다 —
    스탭이 문구를 다 지운 것은 「빈 문자를 보내라」가 아니라 「기본으로
    되돌려라」이기 때문이다.
    """

    kind: GuideMessageKind
    enabled: bool
    body: str | None = None
    #: 소진 며칠 전에 보낼지. `RUN_OUT` 에만 쓴다 — 다른 회차는 날수가 이름에 있다.
    days_before: int | None = None


class MessageRoundOut(MessageRound):
    #: 화면에서 끌 수 없는 회차인가. 「일주일 뒤 (고정)」이 그렇다.
    #: 서버가 정해 내려 준다 — 화면마다 다르게 알면 한쪽에서만 꺼진다.
    fixed: bool = False


class MessagePlanRequest(StrictModel):
    """문자 설정 저장 — 「이 환자만 적용」."""

    #: 확인 · 재진 문자를 몇 시에 보낼지. 안내문은 승인 시각 규칙(18:00)을 따른다.
    check_hour: int
    rounds: list[MessageRound]


class MessagePlanResponse(StrictModel):
    check_hour: int
    rounds: list[MessageRoundOut]
