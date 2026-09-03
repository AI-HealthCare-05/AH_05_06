import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.api_errors import ContractRoute
from app.core.time import clinic_today
from app.dependencies.patient_access import (
    ClinicalActor,
    require_patient_read,
    require_sms_send,
)
from app.dtos.messages import (
    MessagePatchRequest,
    MessagePatchResponse,
    ScheduledMessageListResponse,
    SentMessageListResponse,
)
from app.services.message_export import csv_filename, csv_rows
from app.services.message_history import MessageHistoryService
from app.services.message_schedule import MessageScheduleService

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


@message_router.patch(
    "/{message_id}",
    response_model=MessagePatchResponse,
)
async def update_scheduled_message(
    message_id: int,
    payload: MessagePatchRequest,
    actor: Annotated[ClinicalActor, Depends(require_sms_send)],
    service: Annotated[MessageScheduleService, Depends(MessageScheduleService)],
) -> MessagePatchResponse:
    """예약 문자 시각 변경 또는 예약 취소 — KEY-257."""

    return await service.update_message(
        actor,
        message_id,
        payload,
    )


@message_router.get("/history", response_model=SentMessageListResponse)
async def list_sent_messages(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[MessageHistoryService, Depends(MessageHistoryService)],
    since: Annotated[date, Query(alias="from")],
    until: Annotated[date, Query(alias="to")],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> SentMessageListResponse:
    """발송 이력 — 와이어프레임 S2-4.

    기간의 **시작과 끝**을 받는다. 발송 예정(S2-3)의 「앞으로 며칠」과 다른
    까닭은 묻는 것이 다르기 때문이다 — 저쪽은 앞일이고 이쪽은 지난 일이다.
    """
    page = await service.list_sent(actor, since=since, until=until, limit=limit)
    return SentMessageListResponse(
        from_date=since,
        to_date=until,
        counts=page.counts,
        items=page.items,
        truncated=page.truncated,
    )


@message_router.get("/history.csv")
async def download_sent_messages(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[MessageHistoryService, Depends(MessageHistoryService)],
    since: Annotated[date, Query(alias="from")],
    until: Annotated[date, Query(alias="to")],
) -> StreamingResponse:
    """CSV 내려받기 — 와이어프레임 S2-4 하단.

    **화면과 달리 자르지 않는다.** 표는 「일부 행만 표시」한다고 원문이 적어
    두었고, 이 받기가 그 나머지를 가져가는 자리다 — 여기서도 자르면 둘 다
    일부인 셈이 된다.

    **환자 이름 · 차트번호 · 생년월일이 파일로 나간다.** 화면에 보이는 것과
    같은 값이지만 나가는 방식이 다르므로, 누가 받을 수 있는지는 의원이 정할
    일이다. 지금은 환자 정보를 읽을 수 있는 사람과 같은 권한으로 둔다.
    """
    page = await service.list_sent(actor, since=since, until=until, limit=None)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in csv_rows(page.items):
        writer.writerow(row)

    # 엑셀이 UTF-8 을 알아보게 BOM 을 앞에 둔다 — 없으면 한글이 깨져 열린다.
    body = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([body]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{csv_filename(since, until)}"'},
    )


@message_router.patch(
    "/{message_id}",
    response_model=MessagePatchResponse,
)
async def patch_message(
    message_id: int,
    payload: MessagePatchRequest,
    actor: Annotated[ClinicalActor, Depends(require_sms_send)],
    service: Annotated[
        MessageScheduleService,
        Depends(MessageScheduleService),
    ],
) -> MessagePatchResponse:
    """예약 문자 시각 변경 또는 예약 취소 — KEY-257."""

    return await service.update_message(
        actor,
        message_id,
        payload,
    )
