from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read, require_patient_write
from app.dtos.base import CursorPage
from app.dtos.visits import (
    CheckAnswerResponse,
    CheckAnswerSaveRequest,
    VisitCreateRequest,
    VisitListResponse,
    VisitResponse,
    VisitUpdateRequest,
)
from app.services.visits import VisitCheckService, VisitService

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
    visit = await service.create(actor, patient_id, data)
    return (await service.responses(actor, [visit]))[0]


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
        items=await service.responses(actor, visits),
        page=CursorPage(next_cursor=next_cursor, has_next=has_next),
    )


@visit_router.get("/visits/{visit_id}", response_model=VisitResponse)
async def get_visit(
    visit_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[VisitService, Depends(VisitService)],
) -> VisitResponse:
    visit = await service.get(actor, visit_id)
    return (await service.responses(actor, [visit]))[0]


@visit_router.patch("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    visit_id: int,
    data: VisitUpdateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[VisitService, Depends(VisitService)],
) -> VisitResponse:
    visit = await service.update(actor, visit_id, data)
    return (await service.responses(actor, [visit]))[0]


@visit_router.get("/visits/{visit_id}/check-items", response_model=CheckAnswerResponse)
async def read_check_items(
    visit_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[VisitCheckService, Depends(VisitCheckService)],
) -> CheckAnswerResponse:
    """확인 항목의 답 — 와이어프레임 S1-6.

    물어볼 항목 **전부**를 준다. 아직 안 여쭌 것은 `checked` 가 `null` 이다 —
    답이 있는 것만 주면 화면이 나머지를 스스로 세워야 하고, 그러면 항목 목록이
    두 곳에 생겨 한쪽만 바뀐다.
    """
    return CheckAnswerResponse(**await service.read(actor, visit_id))


@visit_router.put("/visits/{visit_id}/check-items", response_model=CheckAnswerResponse)
async def save_check_items(
    visit_id: int,
    payload: CheckAnswerSaveRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[VisitCheckService, Depends(VisitCheckService)],
) -> CheckAnswerResponse:
    """확인 항목을 저장한다 — **한 판을 통째로**.

    항목 하나씩 받으면 중간에 끊겼을 때 반쪽 상태가 남고, 화면은 그것을
    「안 여쭌 것」과 구별하지 못한다.
    """
    return CheckAnswerResponse(**await service.save(actor, visit_id, payload))
