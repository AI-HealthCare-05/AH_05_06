from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read, require_patient_write
from app.dtos.patients import (
    CursorPage,
    LatestVisitResponse,
    PatientCreateRequest,
    PatientListItem,
    PatientListResponse,
    PatientResponse,
    PatientUpdateRequest,
)
from app.services.patients import PatientService

patient_router = APIRouter(prefix="/patients", tags=["patients"], route_class=ContractRoute)


@patient_router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    data: PatientCreateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[PatientService, Depends(PatientService)],
) -> PatientResponse:
    return PatientResponse.model_validate(await service.create(actor, data))


@patient_router.get("", response_model=PatientListResponse)
async def list_patients(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[PatientService, Depends(PatientService)],
    keyword: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PatientListResponse:
    rows, next_cursor, has_next = await service.list(
        actor,
        keyword=keyword,
        cursor=cursor,
        limit=limit,
    )
    items = []
    for patient, latest_visit in rows:
        response = PatientListItem.model_validate(patient)
        if latest_visit is not None:
            response.latest_visit = LatestVisitResponse.model_validate(latest_visit)
        items.append(response)
    return PatientListResponse(items=items, page=CursorPage(next_cursor=next_cursor, has_next=has_next))


@patient_router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[PatientService, Depends(PatientService)],
) -> PatientResponse:
    return PatientResponse.model_validate(await service.get(actor, patient_id))


@patient_router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    data: PatientUpdateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[PatientService, Depends(PatientService)],
) -> PatientResponse:
    return PatientResponse.model_validate(await service.update(actor, patient_id, data))
