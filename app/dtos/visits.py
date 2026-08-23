from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.dtos.base import BaseSerializerModel
from app.dtos.patients import CursorPage
from app.models.visits import VisitStatus


class VisitCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: int | None = None
    department_id: int | None = None
    visited_at: datetime
    visit_summary: str | None = None
    doctor_note: str | None = None
    status: VisitStatus = VisitStatus.COMPLETED
    planned_stop: bool = False


class VisitUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: int | None = None
    department_id: int | None = None
    visited_at: datetime | None = None
    visit_summary: Annotated[str | None, Field(default=None, max_length=10000)]
    doctor_note: Annotated[str | None, Field(default=None, max_length=10000)]
    status: VisitStatus | None = None
    planned_stop: bool | None = None


class DoctorResponse(BaseModel):
    doctor_id: int
    name: str


class VisitResponse(BaseSerializerModel):
    visit_id: int
    patient_id: int
    doctor_id: int | None
    doctor: DoctorResponse | None = None
    department: str | None
    visited_at: datetime
    visit_summary: str | None
    doctor_note: str | None
    status: VisitStatus
    planned_stop: bool
    created_at: datetime
    updated_at: datetime


class VisitListResponse(BaseModel):
    items: list[VisitResponse]
    page: CursorPage
