from pydantic import BaseModel, ConfigDict


class BaseSerializerModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CursorPage(BaseModel):
    """쪽 나눔 — 다음 쪽으로 가는 열쇠와 「더 있나」.

    **환자 DTO 에 있던 것을 여기로 옮겼다.** 담는 것이 환자와 아무 상관 없는
    쪽 나눔 모양인데 `dtos/patients.py` 에 살고 있어서, 환자 DTO 가 다른 DTO
    를 부르는 순간 고리가 생겼다 — `patients → visits → patients`.
    """

    next_cursor: str | None
    has_next: bool
