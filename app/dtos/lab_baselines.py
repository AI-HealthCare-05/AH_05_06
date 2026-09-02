"""검사 기준선 — 와이어프레임 D2-4."""

from decimal import Decimal

from pydantic import BaseModel

from app.dtos.visits import DoctorResponse
from app.models.catalog import BaselineDirection, SetDisease


class LabBaselineItem(BaseModel):
    disease: SetDisease
    name: str
    direction: BaselineDirection
    #: **비워 둘 수 있다.** 원문: 「비워 두면 값과 추이만 표시하고 목표 대비
    #: 수치는 계산하지 않습니다」.
    low: Decimal | None = None
    high: Decimal | None = None
    by_age: bool = False
    #: 판독이 진료기록에서 찾을 표기들 — EMR 마다 다르다.
    keywords: str = ""
    unit: str = ""
    always_shown: bool = True


class LabBaselineListResponse(BaseModel):
    #: 비면 의원 공통이다. 원문의 「누구 기준」.
    doctor_id: int | None
    items: list[LabBaselineItem]
    #: **의사가 둘 이상일 때만** 화면이 「누구 기준」을 보인다(원문).
    doctors: list[DoctorResponse]


class LabBaselineSaveRequest(BaseModel):
    items: list[LabBaselineItem]
