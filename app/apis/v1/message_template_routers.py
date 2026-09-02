from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dtos.message_templates import (
    MessageTemplateItem,
    MessageTemplateListResponse,
    MessageTemplateSaveRequest,
)
from app.models.catalog import MessageTemplateKind
from app.services.message_templates import (
    DEFAULT_BODY,
    KNOWN_VARIABLES,
    REQUIRED_VARIABLES,
    SMS_LIMIT,
    SYSTEM_BODY,
    MessageTemplateService,
)

message_template_router = APIRouter(prefix="/message-templates", tags=["message-templates"], route_class=ContractRoute)


def _item(kind: MessageTemplateKind, edited: dict[MessageTemplateKind, str]) -> MessageTemplateItem:
    body = edited.get(kind)
    return MessageTemplateItem(
        kind=kind,
        body=body if body is not None else DEFAULT_BODY[kind],
        default_body=DEFAULT_BODY[kind],
        is_default=body is None,
        required_variables=list(REQUIRED_VARIABLES[kind]),
    )


def _page(edited: dict[MessageTemplateKind, str]) -> MessageTemplateListResponse:
    return MessageTemplateListResponse(
        items=[_item(kind, edited) for kind in MessageTemplateKind],
        known_variables=sorted(KNOWN_VARIABLES),
        sms_limit=SMS_LIMIT,
        system_body=SYSTEM_BODY,
    )


@message_template_router.get("", response_model=MessageTemplateListResponse)
async def list_message_templates(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[MessageTemplateService, Depends(MessageTemplateService)],
) -> MessageTemplateListResponse:
    """문자 문구 — 와이어프레임 D2-5.

    **보는 것은 스탭도, 고치는 것은 의사만이다.** 원문: 「수정은 의사 계정만
    — 문자도 환자에게 가는 안내다 · 스탭은 열람」.
    """
    return _page(await service.list(actor))


@message_template_router.put("/{kind}", response_model=MessageTemplateListResponse)
async def save_message_template(
    kind: MessageTemplateKind,
    data: MessageTemplateSaveRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[MessageTemplateService, Depends(MessageTemplateService)],
) -> MessageTemplateListResponse:
    """원문: 「저장 → 다음 발송부터 적용」. 이미 예약된 문자도 그 문구로 나간다 —
    `GuideMessage` 가 본문을 미리 굳혀 두지 않기 때문이다."""
    await service.save(actor, kind, data.body)
    return _page(await service.list(actor))


@message_template_router.delete("/{kind}", response_model=MessageTemplateListResponse)
async def reset_message_template(
    kind: MessageTemplateKind,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[MessageTemplateService, Depends(MessageTemplateService)],
) -> MessageTemplateListResponse:
    """원문 「원본으로 되돌리기」 — **줄을 지운다.**"""
    await service.reset(actor, kind)
    return _page(await service.list(actor))
