from datetime import date, datetime

from pydantic import BaseModel

from app.dtos.patients import CursorPage
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
