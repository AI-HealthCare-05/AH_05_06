from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dtos.messages import ScheduledMessageListResponse
from app.services.message_schedule import MessageScheduleService, clinic_today

message_router = APIRouter(prefix="/messages", tags=["messages"], route_class=ContractRoute)


@message_router.get("/scheduled", response_model=ScheduledMessageListResponse)
async def list_scheduled_messages(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[MessageScheduleService, Depends(MessageScheduleService)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ScheduledMessageListResponse:
    """발송 예정 — 와이어프레임 S2-3.

    **스탭도 본다.** 이 화면이 잡으라는 것(잘못된 번호 · 문자 잔량)이 스탭이
    손댈 일이라, 의사만 여는 자리로 두면 화면의 뜻이 없어진다.
    """
    page = await service.list_scheduled(actor, days=days, today=clinic_today(), limit=limit)
    return ScheduledMessageListResponse(
        days=days,
        counts=page.counts,
        items=page.items,
        truncated=page.truncated,
    )
