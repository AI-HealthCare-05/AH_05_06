"""안내문 검토·승인·반려 — KEY-111 (와이어프레임 D1-1~D1-5).

권한은 **서비스가 판단한다**(`app/services/guides.py`) — 라우터는 누가 왔는지만
넘긴다. 「승인은 의사만」은 규칙이고, 규칙은 서비스에 있다(`docs/models-layout.md`).
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.time import DISPLAY_TIMEZONE
from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.guides import GuideResponse, PatientHead, ReturnRequest, SectionEditRequest, SectionResponse
from app.models.visits import GuideDocument, GuideSection, GuideSectionKey
from app.services.guides import GuideService

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
    today = datetime.now(DISPLAY_TIMEZONE).date()
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
        sections=[_section(s) for s in sorted(guide.sections, key=_section_order)],
    )


#: 계약이 정한 차례 — `GuideSectionKey` 에 적힌 순서 그대로다(P2 · P3 · P4, 그리고
#: 문자 설정). `emergency` 는 `caution` 바로 뒤다.
_SECTION_ORDER: dict[GuideSectionKey, int] = {key: i for i, key in enumerate(GuideSectionKey)}


def _section_order(section: GuideSection) -> int:
    """**차례를 삽입 순서에 맡기지 않는다.**

    예전에는 `guide_section_id` 로 정렬했다. 지금 생성 경로가 계약 순서대로
    넣으니 결과는 같지만, 그건 **우연히 같은 것**이다. 행 하나를 나중에
    끼워 넣으면(예: 기존 안내문에 `emergency` 를 채워 넣는 backfill) 그 행이
    맨 뒤로 가고, 응급 문장이 문자 설정 뒤에 붙는다.

    계약(`docs/api/hospital.md` §5)은 **차례까지** 정한다. 그러면 차례는
    계약에서 읽어야지 DB 가 준 순서에서 읽을 것이 아니다 (KEY-161).
    """
    return _SECTION_ORDER[GuideSectionKey(section.section_key)]


def _section(section: GuideSection) -> SectionResponse:
    return SectionResponse(
        key=section.section_key,
        body=section.body,
        edited=section.edited_body is not None,
        locked=section.locked,
        warn=section.warn,
    )


@guide_router.post("/{visit_id}/guide/generate", response_model=GuideResponse, status_code=status.HTTP_201_CREATED)
async def generate_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.generate(actor, visit_id)
    await guide.fetch_related("sections", "visit__patient")
    return _to_response(guide)


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
