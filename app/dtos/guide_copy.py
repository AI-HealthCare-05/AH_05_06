"""안내문 고치기 — 와이어프레임 D2-1 · D2-2."""

from pydantic import BaseModel

from app.models.catalog import CautionSectionKey, SetDisease


class CopySectionItem(BaseModel):
    section_key: CautionSectionKey
    #: 승인된 원본(식약처 허가사항 자리). 없으면 그 세트에 승인 문구가 없다.
    origin: str | None
    #: 원장님 문구. 없으면 원본이 그대로 나간다.
    body: str | None
    #: 🚨 응급은 열리지 않는다 — 원문이 못박는다.
    editable: bool


class CopySetItem(BaseModel):
    prescription_set_id: int
    name: str
    disease: SetDisease
    sections: list[CopySectionItem]
    #: 「확인 완료」를 눌렀는가. **고치면 풀린다.**
    reviewed: bool


class CopyDefaultItem(BaseModel):
    """아직 아무도 안 고쳤을 때 쓰는 **기본 문구.**

    아직 만들지 않은 처방에도 이 글이 쓰인다 — 그래서 만들기 화면이 미리
    보여 줄 수 있어야 한다. 화면이 문장을 베껴 두면 두 곳이 갈라진다:
    한동안 `guides.py` 가 제 것을 따로 들고 있어서 설정 화면이 **실제로는
    나가지 않는 글**을 원본이라며 보였다.
    """

    section_key: CautionSectionKey
    body: str
    editable: bool


class GuideCopyListResponse(BaseModel):
    #: 비면 의원 공통 문구다.
    doctor_id: int | None = None
    items: list[CopySetItem]
    #: 갈래별 기본 문구. **아직 없는 처방**의 화면이 이것을 보인다.
    defaults: list[CopyDefaultItem] = []


class GuideCopySaveRequest(BaseModel):
    body: str
