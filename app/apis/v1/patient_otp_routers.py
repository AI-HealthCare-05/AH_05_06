"""환자 링크 OTP API — KEY-91."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dtos.patient_otp import (
    PatientOtpIssueRequest,
    PatientOtpIssueResponse,
    PatientOtpVerifyRequest,
    PatientOtpVerifyResponse,
)
from app.services.patient_otp import OTP_TTL, PatientOtpService, UnavailableOtpDelivery

patient_otp_router = APIRouter(prefix="/patient-auth/otp", tags=["patient-auth"])


def _otp_service() -> PatientOtpService:
    return PatientOtpService(UnavailableOtpDelivery())


@patient_otp_router.post("/issue", response_model=PatientOtpIssueResponse)
async def issue_patient_otp(
    payload: PatientOtpIssueRequest,
    service: Annotated[PatientOtpService, Depends(_otp_service)],
) -> PatientOtpIssueResponse:
    challenge = await service.issue(payload.link_token)
    return PatientOtpIssueResponse(
        expires_at=challenge.expires_at,
        retry_after_seconds=int(OTP_TTL.total_seconds()),
    )


@patient_otp_router.post("/verify", response_model=PatientOtpVerifyResponse)
async def verify_patient_otp(
    payload: PatientOtpVerifyRequest,
    service: Annotated[PatientOtpService, Depends(_otp_service)],
) -> PatientOtpVerifyResponse:
    await service.verify(payload.link_token, payload.code)
    return PatientOtpVerifyResponse()
