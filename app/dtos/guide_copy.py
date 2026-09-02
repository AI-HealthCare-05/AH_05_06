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


class GuideCopyListResponse(BaseModel):
    doctor_id: int
    items: list[CopySetItem]


class GuideCopySaveRequest(BaseModel):
    body: str
