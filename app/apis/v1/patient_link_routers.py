"""개발용 환자 링크 API — KEY-90 (8/27 Walking Skeleton)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.patient_links import (
    PatientGuideResponse,
    PatientGuideSectionResponse,
    PatientLinkIssueResponse,
)
from app.models.visits import GuideDocument, PatientGuideLink
from app.services.patient_links import PatientLinkService

patient_link_management_router = APIRouter(prefix="/visits", tags=["patient-links"])
patient_guide_router = APIRouter(prefix="/guides", tags=["patient-guides"])


def _service() -> PatientLinkService:
    return PatientLinkService()


@patient_link_management_router.post(
    "/{visit_id}/guide/link",
    response_model=PatientLinkIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_patient_guide_link(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[PatientLinkService, Depends(_service)],
) -> PatientLinkIssueResponse:
    link, raw_token = await service.issue(actor, visit_id)
    return PatientLinkIssueResponse(
        path=f"/api/v1/guides/{raw_token}",
        expires_at=link.expires_at,
    )


def _patient_response(link: PatientGuideLink, guide: GuideDocument) -> PatientGuideResponse:
    if guide.approved_at is None:
        # 서비스가 앞에서 막아야 하는 불변식이다. 최적화 모드에서 사라지는
        # assert에 응답 안전을 맡기지 않는다.
        raise RuntimeError("approved guide has no approved_at")
    return PatientGuideResponse(
        version=guide.version,
        approved_at=guide.approved_at,
        expires_at=link.expires_at,
        sections=[
            PatientGuideSectionResponse(key=section.section_key, body=section.body)
            for section in sorted(guide.sections, key=lambda item: item.guide_section_id)
        ],
    )


@patient_guide_router.get("/{token}", response_model=PatientGuideResponse)
async def read_patient_guide(
    token: str,
    service: Annotated[PatientLinkService, Depends(_service)],
) -> PatientGuideResponse:
    link, guide = await service.get_approved_guide(token)
    return _patient_response(link, guide)
