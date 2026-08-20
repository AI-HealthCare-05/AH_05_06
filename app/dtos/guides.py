"""안내문 응답 모양 — KEY-111.

**화면이 이미 쓰고 있는 이름을 그대로 쓴다.** `#48`(KEY-86)의
`frontend/js/doctor-api.js` 가 목업으로 이 모양을 쓰고 있어서, 여기서
이름을 바꾸면 화면을 다시 고쳐야 한다. 계약을 먼저 적어 두고 양쪽이
같은 것을 보는 것이 이 파일의 목적이다.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.visits import GuideSectionKey, GuideStatus


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


class GuideResponse(StrictModel):
    visit_id: int
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
