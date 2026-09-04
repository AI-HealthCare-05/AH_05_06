from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dtos.guide_copy import (
    CopyDefaultItem,
    CopySectionItem,
    CopySetItem,
    GuideCopyListResponse,
    GuideCopySaveRequest,
)
from app.models.catalog import CautionSectionKey
from app.services import guide_defaults
from app.services.guide_copy import GuideCopyService

guide_copy_router = APIRouter(prefix="/guide-copy", tags=["guide-copy"], route_class=ContractRoute)


def _whose(actor: ClinicalActor, doctor_id: int | None) -> int | None:
    """**누구 문구를 보는가.** 물어본 사람이 있으면 그 사람, 없으면 의원 공통.

    전에는 스탭이 번호 없이 열면 `400 DOCTOR_REQUIRED` 였다 — 스탭은 볼 수만
    있으니 누구 것을 볼지 골라야 한다는 뜻이었다. 그런데 **화면에는 고르는
    칸이 없었고**(`frontend/js/settings.js` 가 번호 없이 부른다), 그래서
    스탭이 안내문 문구 화면을 열면 그냥 「불러오지 못했습니다」가 떴다.

    **번호를 안 주면 의원 공통이다**(`None`). 한동안 제 것을 줬는데, 그러면
    같은 처방을 원장 A 와 B 가 열었을 때 **문구만 서로 다르게 보인다** — 약도
    일수도 확인 항목도 의원 공통인데(처방 세트에 의사 칸이 없다) 그 위에
    덧씌우는 표현만 개인 것이었다. 2026-09-02 회의 결정(「기본 설정은 모두
    공통으로 두자」)과도 어긋났다.

    번호를 주면 그 사람 것을 본다 — 원장별 문구는 그 길로 나중에 열린다.
    지금 화면에는 고르는 칸이 없어 늘 의원 공통이다.
    """
    return doctor_id


def _writer(actor: ClinicalActor, doctor_id: int | None = None) -> int | None:
    """**고치는 자리도 읽는 자리와 같아야 한다.**

    번호를 안 주면 의원 공통을 고친다. 읽기가 의원 공통을 보이는데 쓰기가 제
    것에 저장하면, 고치고 나서 다시 열었을 때 **안 바뀐 것처럼 보인다** —
    고친 것은 개인 자리에 들어갔고 화면은 공통 자리를 보이기 때문이다.

    역할은 안 본다. 2026-09-02 회의에서 설정 수정을 스탭에게도 열었고, 여기
    있던 「의사만」 검사가 **같은 규칙의 다섯 번째 복제**였다 —
    `guide_copy.py` · `lab_baselines.py` · `message_templates.py` ·
    `catalog/api.py` 그리고 여기. 서비스가 소유로 막으므로 이 자리는 누구인지
    말해 주기만 한다.
    """
    return doctor_id


async def _page(service: GuideCopyService, actor: ClinicalActor, doctor_id: int | None) -> GuideCopyListResponse:
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
        defaults=[
            CopyDefaultItem(
                section_key=key,
                body=body,
                editable=key in guide_defaults.EDITABLE_SECTIONS,
            )
            for key, body in guide_defaults.BY_SECTION.items()
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
