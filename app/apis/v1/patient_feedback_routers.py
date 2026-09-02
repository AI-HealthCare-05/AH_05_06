"""Patient feedback submission API for KEY-239."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.api_errors import ContractRoute
from app.dependencies.patient_auth import require_patient_feedback_session
from app.dtos.patient_feedback import PatientFeedbackCreateRequest, PatientFeedbackCreateResponse
from app.services.patient_feedback import PatientFeedbackService

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
