"""개발용 환자 링크 API — KEY-90 (8/27 Walking Skeleton)."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, status

from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.checkins import (
    CheckInAnswerContent,
    CheckInCreateRequest,
    CheckInPainResponse,
    CheckInPainTypeResponse,
    CheckInReadResponse,
    CheckInSaveResponse,
    HospitalCheckInResponse,
    PainType,
)
from app.dtos.patient_links import (
    PatientGuideResponse,
    PatientGuideSectionResponse,
    PatientLinkIssueResponse,
)
from app.models.visits import CheckIn, CheckInMedication, GuideDocument, PatientGuideLink
from app.services.checkins import CheckInService, approved_answer_bodies
from app.services.patient_links import PatientLinkService

patient_link_management_router = APIRouter(prefix="/visits", tags=["patient-links"])
patient_guide_router = APIRouter(prefix="/guides", tags=["patient-guides"])
patient_checkin_router = APIRouter(prefix="/checkins", tags=["patient-checkins"])


def _service() -> PatientLinkService:
    return PatientLinkService()


def _checkin_service() -> CheckInService:
    return CheckInService()


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


def _pain_response(check_in: CheckIn) -> CheckInPainResponse | None:
    if check_in.pain_had is None:
        return None
    return CheckInPainResponse(
        had=check_in.pain_had,
        score=check_in.pain_score,
        types=[cast(PainType, item) for item in check_in.pain_types],
    )


@patient_checkin_router.get("/{token}", response_model=CheckInReadResponse)
async def read_patient_checkin(
    token: str,
    service: Annotated[CheckInService, Depends(_checkin_service)],
) -> CheckInReadResponse:
    guide, answered = await service.read_form(token)
    medication, caution = approved_answer_bodies(guide)
    return CheckInReadResponse(
        answers={
            CheckInMedication.TAKING: None,
            CheckInMedication.UNCOMFORTABLE: CheckInAnswerContent(lead=caution),
            CheckInMedication.MISSING: CheckInAnswerContent(lead=medication),
            CheckInMedication.STOPPED_SIDE_EFFECT: CheckInAnswerContent(lead=caution),
            CheckInMedication.STOPPED_IMPROVED: CheckInAnswerContent(lead=medication),
        },
        pain_types=[
            CheckInPainTypeResponse(key="menstrual", label="월경통"),
            CheckInPainTypeResponse(key="intercourse", label="성교통"),
            CheckInPainTypeResponse(key="defecation", label="배변통"),
            CheckInPainTypeResponse(key="chronic_pelvic", label="만성골반통"),
        ],
        answered=answered,
    )


@patient_checkin_router.post("/{token}", response_model=CheckInSaveResponse, status_code=status.HTTP_201_CREATED)
async def save_patient_checkin(
    token: str,
    payload: CheckInCreateRequest,
    service: Annotated[CheckInService, Depends(_checkin_service)],
) -> CheckInSaveResponse:
    check_in = await service.save(token, payload)
    return CheckInSaveResponse(
        check_in_id=check_in.check_in_id,
        medication=check_in.medication,
        pain=_pain_response(check_in),
    )


@patient_link_management_router.get("/{visit_id}/checkin", response_model=HospitalCheckInResponse)
async def read_hospital_checkin(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[CheckInService, Depends(_checkin_service)],
) -> HospitalCheckInResponse:
    check_in = await service.get_for_hospital(actor, visit_id)
    return HospitalCheckInResponse(
        check_in_id=check_in.check_in_id,
        visit_id=visit_id,
        medication=check_in.medication,
        pain=_pain_response(check_in),
        submitted_at=check_in.created_at,
    )
