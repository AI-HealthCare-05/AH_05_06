"""문자 문구 — 와이어프레임 D2-5."""

from pydantic import BaseModel

from app.models.catalog import MessageTemplateKind


class MessageTemplateItem(BaseModel):
    """문구 한 칸.

    **기본 문구를 함께 보낸다.** 화면의 「원본으로 되돌리기」가 무엇으로
    돌아가는지 보여 줘야 하고, 「지금 기본값인가」도 그 둘을 견줘 알 수 있다.
    """

    kind: MessageTemplateKind
    body: str
    default_body: str
    #: 고친 적이 없어 기본 문구를 그대로 쓰는가.
    is_default: bool
    #: 지울 수 없는 변수 — 원문 「{링크}는 지울 수 없다」.
    required_variables: list[str]


class MessageTemplateListResponse(BaseModel):
    items: list[MessageTemplateItem]
    #: 넣을 수 있는 변수 전부. 화면이 「쓸 수 있는 변수」로 보인다.
    known_variables: list[str]
    #: 90바이트를 넘으면 장문(LMS)이 되어 단가가 달라진다.
    sms_limit: int
    #: **고칠 수 없는 문자.** 원문 「인증번호 / 수정 불가 · 시스템」.
    #: 무엇이 나가는지는 알아야 하고, 손댈 수는 없다.
    system_body: str


class MessageTemplateSaveRequest(BaseModel):
    body: str
