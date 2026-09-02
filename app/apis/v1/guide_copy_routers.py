from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.api_errors import ApiError, ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dtos.guide_copy import (
    CopySectionItem,
    CopySetItem,
    GuideCopyListResponse,
    GuideCopySaveRequest,
)
from app.models.catalog import CautionSectionKey
from app.services.guide_copy import GuideCopyService

guide_copy_router = APIRouter(prefix="/guide-copy", tags=["guide-copy"], route_class=ContractRoute)


def _whose(actor: ClinicalActor, doctor_id: int | None) -> int:
    """**누구 문구를 보는가.**

    의사가 열면 제 것을, 스탭이 열면 물어본 의사 것을 본다 — 스탭은 볼 수만
    있으므로 누구 것을 보는지 골라야 한다. 아무도 안 정해 주면 답할 수 없다:
    「의원 공통 문구」라는 것이 없고, 그 자리는 원본이다.
    """
    if doctor_id is not None:
        return doctor_id
    if "doctor" in actor.roles:
        return actor.staff_id
    raise ApiError(400, "DOCTOR_REQUIRED", "어느 의사의 문구를 볼지 골라 주세요.")


def _writer(actor: ClinicalActor) -> int:
    """**고치는 사람은 늘 자기 자신이다.**

    읽기와 달리 「누구 것을 고칠까」를 물을 여지가 없다 — 남의 이름으로 말하는
    일이기 때문이다. 스탭에게는 「골라 주세요」(400)가 아니라 「의사만
    고칩니다」(403)가 맞는 답이라 여기서 먼저 가른다.
    """
    if "doctor" not in actor.roles:
        raise ApiError(403, "DOCTOR_ONLY", "안내문 문구는 의사 계정만 수정할 수 있습니다.")
    return actor.staff_id


async def _page(service: GuideCopyService, actor: ClinicalActor, doctor_id: int) -> GuideCopyListResponse:
    return GuideCopyListResponse(
        doctor_id=doctor_id,
        items=[
            CopySetItem(
                prescription_set_id=row.prescription_set_id,
                name=row.name,
                disease=row.disease,
                sections=[
                    CopySectionItem(
                        section_key=part.section_key,
                        origin=part.origin,
                        body=part.body,
                        editable=part.editable,
                    )
                    for part in row.sections
                ],
                reviewed=row.reviewed,
            )
            for row in await service.list(actor, doctor_id=doctor_id)
        ],
    )


@guide_copy_router.get("", response_model=GuideCopyListResponse)
async def list_guide_copy(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[GuideCopyService, Depends(GuideCopyService)],
    doctor_id: int | None = None,
) -> GuideCopyListResponse:
    """안내문 — 와이어프레임 D2-1 · D2-2.

    **원본은 손대지 않는다.** 이 응답의 `origin` 은 승인된 자료
    (`drug_caution_content`)이고, `body` 는 그 위에 덧씌운 표현이다.
    """
    return await _page(service, actor, _whose(actor, doctor_id))


@guide_copy_router.put("/{prescription_set_id}/{section_key}", response_model=GuideCopyListResponse)
async def save_guide_copy(
    prescription_set_id: int,
    section_key: CautionSectionKey,
    data: GuideCopySaveRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[GuideCopyService, Depends(GuideCopyService)],
) -> GuideCopyListResponse:
    """원문 「저장 → D2-1 로 · 그 자리에 원장님 문구가 들어간다」."""
    doctor_id = _writer(actor)
    await service.save(
        actor,
        doctor_id=doctor_id,
        prescription_set_id=prescription_set_id,
        section_key=section_key,
        body=data.body,
    )
    return await _page(service, actor, doctor_id)


@guide_copy_router.delete("/{prescription_set_id}/{section_key}", response_model=GuideCopyListResponse)
async def revert_guide_copy(
    prescription_set_id: int,
    section_key: CautionSectionKey,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[GuideCopyService, Depends(GuideCopyService)],
) -> GuideCopyListResponse:
    """원문 「원본으로 되돌리기 → 덮어쓴 것을 지우고 원본으로 되돌린다」."""
    doctor_id = _writer(actor)
    await service.revert(actor, doctor_id=doctor_id, prescription_set_id=prescription_set_id, section_key=section_key)
    return await _page(service, actor, doctor_id)


@guide_copy_router.post("/{prescription_set_id}/review", response_model=GuideCopyListResponse)
async def review_guide_copy(
    prescription_set_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[GuideCopyService, Depends(GuideCopyService)],
) -> GuideCopyListResponse:
    """원문 「확인 완료 → 다음 약으로 · 5장이면 끝난다」."""
    doctor_id = _writer(actor)
    await service.review(actor, doctor_id=doctor_id, prescription_set_id=prescription_set_id)
    return await _page(service, actor, doctor_id)
