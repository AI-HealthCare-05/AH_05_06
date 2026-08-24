"""안내문 검토·승인·반려 — KEY-111 (와이어프레임 D1-1~D1-5).

권한은 **서비스가 판단한다**(`app/services/guides.py`) — 라우터는 누가 왔는지만
넘긴다. 「승인은 의사만」은 규칙이고, 규칙은 서비스에 있다(`docs/models-layout.md`).
"""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, status

from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.guides import GuideResponse, PatientHead, ReturnRequest, SectionEditRequest, SectionResponse
from app.models.visits import GuideDocument, GuideSection
from app.services.guides import GuideService

SEOUL = ZoneInfo("Asia/Seoul")

# develop에서 추가된 generate 라우트가 병합될 때도 공통 인증 의존성을
# 사용하도록 이전 내부 이름을 구현 복제 없이 연결한다.
_Actor = StaffActor
_actor = get_staff_actor

guide_router = APIRouter(prefix="/visits", tags=["guides"])


def _service() -> GuideService:
    return GuideService()


def _age_on(birth_date: date, today: date) -> int:
    """만 나이. 생일이 아직 안 지났으면 한 살 뺀다.

    계약 §4 — 「`age` 는 저장값이 아니라 **요청한 현지 날짜**와 `birth_date` 로
    계산한다」. 저장해 두면 시간이 지나면서 조용히 틀린 값이 된다.
    """
    before_birthday = (today.month, today.day) < (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (1 if before_birthday else 0)


def _to_response(guide: GuideDocument) -> GuideResponse:
    visit = guide.visit
    patient = visit.patient
    today = datetime.now(SEOUL).date()
    return GuideResponse(
        visit_id=guide.visit_id,
        patient=PatientHead(
            name=patient.name,
            birth_date=patient.birth_date,
            age=_age_on(patient.birth_date, today),
            gender=patient.gender,
            hospital_patient_no=patient.hospital_patient_no,
        ),
        summary=visit.visit_summary,
        status=guide.status,
        version=guide.version,
        approved_at=guide.approved_at,
        scheduled_at=guide.scheduled_at,
        returned_reason=guide.returned_reason,
        sections=[_section(s) for s in sorted(guide.sections, key=lambda s: s.guide_section_id)],
    )


def _section(section: GuideSection) -> SectionResponse:
    return SectionResponse(
        key=section.section_key,
        body=section.body,
        edited=section.edited_body is not None,
        locked=section.locked,
        warn=section.warn,
    )


@guide_router.get("/{visit_id}/guide", response_model=GuideResponse)
async def read_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    return _to_response(await service.get(actor, visit_id))


@guide_router.patch("/{visit_id}/guide/sections/{key}", response_model=SectionResponse)
async def edit_section(
    visit_id: int,
    key: str,
    body: SectionEditRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> SectionResponse:
    return _section(await service.edit_section(actor, visit_id, key, body.body))


@guide_router.post("/{visit_id}/guide/approve", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def approve_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.approve(actor, visit_id)
    await guide.fetch_related("sections", "visit__patient")
    return _to_response(guide)


@guide_router.post("/{visit_id}/guide/return", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def return_guide(
    visit_id: int,
    body: ReturnRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.return_to_staff(actor, visit_id, body.reason)
    await guide.fetch_related("sections", "visit__patient")
    return _to_response(guide)
