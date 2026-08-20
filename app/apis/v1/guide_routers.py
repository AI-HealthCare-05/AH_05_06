"""안내문 검토·승인·반려 — KEY-111 (와이어프레임 D1-1~D1-5).

권한은 **서비스가 판단한다**(`app/services/guides.py`) — 라우터는 누가 왔는지만
넘긴다. 「승인은 의사만」은 규칙이고, 규칙은 서비스에 있다(`docs/models-layout.md`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies.staff_auth import get_current_staff
from app.dtos.guides import GuideResponse, ReturnRequest, SectionEditRequest, SectionResponse
from app.models.staffs import Staff
from app.models.visits import GuideDocument, GuideSection
from app.services.guides import GuideService

guide_router = APIRouter(prefix="/visits", tags=["guides"])


def _service() -> GuideService:
    return GuideService()


class _Actor:
    """서비스가 보는 것은 「누구인가」뿐이다.

    `Staff` 를 그대로 넘기지 않는 이유는, 서비스가 모델에 매이면 나중에
    다른 인증 경로(어드민 · 배치)가 같은 규칙을 못 쓰기 때문이다.
    """

    def __init__(self, staff: Staff) -> None:
        self.user_id = staff.staff_id
        self.hospital_id = staff.hospital_id
        self.roles = frozenset(staff.roles or [])


def _actor(staff: Annotated[Staff, Depends(get_current_staff)]) -> _Actor:
    return _Actor(staff)


def _to_response(guide: GuideDocument) -> GuideResponse:
    return GuideResponse(
        visit_id=guide.visit_id,
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
    actor: Annotated[_Actor, Depends(_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    return _to_response(await service.get(actor, visit_id))


@guide_router.patch("/{visit_id}/guide/sections/{key}", response_model=SectionResponse)
async def edit_section(
    visit_id: int,
    key: str,
    body: SectionEditRequest,
    actor: Annotated[_Actor, Depends(_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> SectionResponse:
    return _section(await service.edit_section(actor, visit_id, key, body.body))


@guide_router.post("/{visit_id}/guide/approve", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def approve_guide(
    visit_id: int,
    actor: Annotated[_Actor, Depends(_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.approve(actor, visit_id)
    await guide.fetch_related("sections")
    return _to_response(guide)


@guide_router.post("/{visit_id}/guide/return", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def return_guide(
    visit_id: int,
    body: ReturnRequest,
    actor: Annotated[_Actor, Depends(_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.return_to_staff(actor, visit_id, body.reason)
    await guide.fetch_related("sections")
    return _to_response(guide)
