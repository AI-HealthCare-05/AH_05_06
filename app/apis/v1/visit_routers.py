from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read, require_patient_write
from app.dtos.patients import CursorPage
from app.dtos.visits import VisitCreateRequest, VisitListResponse, VisitResponse, VisitUpdateRequest
from app.services.visits import VisitService

visit_router = APIRouter(tags=["visits"], route_class=ContractRoute)


@visit_router.post(
    "/patients/{patient_id}/visits",
    response_model=VisitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_visit(
    patient_id: int,
    data: VisitCreateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[VisitService, Depends(VisitService)],
) -> VisitResponse:
    return VisitResponse.model_validate(await service.create(actor, patient_id, data))


@visit_router.get("/patients/{patient_id}/visits", response_model=VisitListResponse)
async def list_visits(
    patient_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[VisitService, Depends(VisitService)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> VisitListResponse:
    visits, next_cursor, has_next = await service.list(
        actor,
        patient_id,
        cursor=cursor,
        limit=limit,
    )
    return VisitListResponse(
        items=[VisitResponse.model_validate(visit) for visit in visits],
        page=CursorPage(next_cursor=next_cursor, has_next=has_next),
    )


@visit_router.get("/visits/{visit_id}", response_model=VisitResponse)
async def get_visit(
    visit_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[VisitService, Depends(VisitService)],
) -> VisitResponse:
    return VisitResponse.model_validate(await service.get(actor, visit_id))


@visit_router.patch("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    visit_id: int,
    data: VisitUpdateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[VisitService, Depends(VisitService)],
) -> VisitResponse:
    return VisitResponse.model_validate(await service.update(actor, visit_id, data))
