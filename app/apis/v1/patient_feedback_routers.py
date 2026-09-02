"""Patient feedback submission API for KEY-239."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.api_errors import ContractRoute
from app.dependencies.patient_auth import require_patient_feedback_session
from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.patient_feedback import (
    AdminPatientFeedbackListResponse,
    PatientFeedbackCreateRequest,
    PatientFeedbackCreateResponse,
)
from app.models.feedback import PatientFeedbackCategory, PatientFeedbackTarget
from app.services.patient_feedback import AdminPatientFeedbackService, PatientFeedbackService

patient_feedback_router = APIRouter(tags=["patient-feedback"], route_class=ContractRoute)


@patient_feedback_router.post(
    "/patient-feedback",
    response_model=PatientFeedbackCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_feedback(
    data: PatientFeedbackCreateRequest,
    link_digest: Annotated[str, Depends(require_patient_feedback_session)],
    service: Annotated[PatientFeedbackService, Depends(PatientFeedbackService)],
) -> PatientFeedbackCreateResponse:
    feedback = await service.create(link_digest, data)
    return PatientFeedbackCreateResponse(feedback_id=feedback.patient_feedback_id)


@patient_feedback_router.get(
    "/admin/patient-feedback",
    response_model=AdminPatientFeedbackListResponse,
)
async def list_patient_feedback(
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[AdminPatientFeedbackService, Depends(AdminPatientFeedbackService)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    target: PatientFeedbackTarget | None = None,
    category: PatientFeedbackCategory | None = None,
) -> AdminPatientFeedbackListResponse:
    return await service.list(
        actor,
        page=page,
        page_size=page_size,
        target=target,
        category=category,
    )
