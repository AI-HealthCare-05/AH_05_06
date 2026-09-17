from datetime import date, datetime

from pydantic import BaseModel

from app.dtos.base import CursorPage
from app.dtos.visits import DoctorResponse
from app.services.work_category import DetailStatus, WorkCategory


class FrontDeskVisitItem(BaseModel):
    visit_id: int
    patient_id: int
    name: str
    hospital_patient_no: str
    birth_date: date
    age: int
    diagnosis_name: str | None
    doctor: DoctorResponse | None
    visited_at: datetime
    work_category: WorkCategory
    detail_status: DetailStatus


class FrontDeskVisitListResponse(BaseModel):
    date: date
    timezone: str = "Asia/Seoul"
    counts: dict[WorkCategory, int]
    selected_categories: list[WorkCategory]
    items: list[FrontDeskVisitItem]
    page: CursorPage
    #: 문자 수신을 거부해서 목록·counts 양쪽에서 뺀 건수 — KEY-355.
    #:
    #: 조용히 없어지면 스탭이 "어제 그 환자"를 못 찾는다. 화면이 이
    #: 숫자로 "수신 거부 N건은 안내 대상이 아닙니다 — 환자 목록 › 수신
    #: 거부"를 띄운다.
    sms_opt_out_excluded: int = 0
