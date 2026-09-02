from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dtos.lab_baselines import (
    LabBaselineItem,
    LabBaselineListResponse,
    LabBaselineSaveRequest,
)
from app.dtos.visits import DoctorResponse
from app.services.lab_baselines import LabBaselineService

lab_baseline_router = APIRouter(prefix="/lab-baselines", tags=["lab-baselines"], route_class=ContractRoute)


async def _page(service: LabBaselineService, actor: ClinicalActor, doctor_id: int | None) -> LabBaselineListResponse:
    rows, doctors = await service.list(actor, doctor_id=doctor_id)
    return LabBaselineListResponse(
        doctor_id=doctor_id,
        items=[
            LabBaselineItem(
                disease=row.disease,
                name=row.name,
                direction=row.direction,
                low=row.low,
                high=row.high,
                by_age=row.by_age,
                keywords=row.keywords,
                unit=row.unit,
                always_shown=row.always_shown,
            )
            for row in rows
        ],
        doctors=[DoctorResponse(doctor_id=staff.staff_id, name=staff.name) for staff in doctors],
    )


@lab_baseline_router.get("", response_model=LabBaselineListResponse)
async def list_lab_baselines(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[LabBaselineService, Depends(LabBaselineService)],
    doctor_id: Annotated[int | None, Query()] = None,
) -> LabBaselineListResponse:
    """검사 기준선 — 와이어프레임 D2-4.

    **보는 것은 스탭도, 고치는 것은 의사만이다.** 판독 결과 확인 화면이 이
    목록으로 항목을 세우므로 스탭도 무엇이 뜰지 알아야 한다.
    """
    return await _page(service, actor, doctor_id)


@lab_baseline_router.put("", response_model=LabBaselineListResponse)
async def save_lab_baselines(
    data: LabBaselineSaveRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[LabBaselineService, Depends(LabBaselineService)],
    doctor_id: Annotated[int | None, Query()] = None,
) -> LabBaselineListResponse:
    """**한 판 통째로 저장한다** — 줄마다 번호를 주고받으면 지운 줄을 놓친다."""
    await service.save(actor, doctor_id=doctor_id, items=[row.model_dump() for row in data.items])
    return await _page(service, actor, doctor_id)
