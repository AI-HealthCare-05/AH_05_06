from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dtos.front_desk import FrontDeskVisitListResponse
from app.dtos.patients import CursorPage
from app.services.front_desk import FrontDeskService

front_desk_router = APIRouter(prefix="/front-desk", tags=["front-desk"], route_class=ContractRoute)


@front_desk_router.get("/visits", response_model=FrontDeskVisitListResponse)
async def list_front_desk_visits(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[FrontDeskService, Depends(FrontDeskService)],
    date_: Annotated[date, Query(alias="date")],
    categories: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> FrontDeskVisitListResponse:
    items, counts, selected, next_cursor, has_next = await service.list_visits(
        actor,
        target_date=date_,
        categories=categories,
        cursor=cursor,
        limit=limit,
    )
    return FrontDeskVisitListResponse(
        date=date_,
        counts=counts,
        selected_categories=selected,
        items=items,
        page=CursorPage(next_cursor=next_cursor, has_next=has_next),
    )
