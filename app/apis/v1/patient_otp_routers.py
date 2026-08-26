"""환자 링크 OTP API — KEY-91."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from redis.asyncio import Redis

from app.core import config
from app.core.config import Env
from app.core.redis_client import get_redis
from app.dependencies.patient_auth import PATIENT_SESSION_COOKIE_NAME
from app.dtos.patient_otp import (
    PatientOtpIssueRequest,
    PatientOtpIssueResponse,
    PatientOtpVerifyRequest,
    PatientOtpVerifyResponse,
)
from app.services.patient_otp import OTP_RESEND_COOLDOWN, PatientOtpService, UnavailableOtpDelivery
from app.services.patient_sessions import PATIENT_SESSION_SECONDS, PatientSessionStore

patient_otp_router = APIRouter(prefix="/patient-auth/otp", tags=["patient-auth"])


def _otp_service() -> PatientOtpService:
    return PatientOtpService(UnavailableOtpDelivery())


def _patient_sessions(redis: Annotated[Redis, Depends(get_redis)]) -> PatientSessionStore:
    return PatientSessionStore(redis)


def _set_patient_session_cookie(response: Response, raw_session: str) -> None:
    response.set_cookie(
        key=PATIENT_SESSION_COOKIE_NAME,
        value=raw_session,
        httponly=True,
        secure=config.ENV == Env.PROD,
        samesite="lax",
        path="/api/v1",
        domain=config.COOKIE_DOMAIN or None,
        max_age=PATIENT_SESSION_SECONDS,
    )


@patient_otp_router.post("/issue", response_model=PatientOtpIssueResponse)
async def issue_patient_otp(
    payload: PatientOtpIssueRequest,
    service: Annotated[PatientOtpService, Depends(_otp_service)],
) -> PatientOtpIssueResponse:
    challenge = await service.issue(payload.link_token)
    return PatientOtpIssueResponse(
        expires_at=challenge.expires_at,
        retry_after_seconds=int(OTP_RESEND_COOLDOWN.total_seconds()),
    )


@patient_otp_router.post("/verify", response_model=PatientOtpVerifyResponse)
async def verify_patient_otp(
    payload: PatientOtpVerifyRequest,
    response: Response,
    service: Annotated[PatientOtpService, Depends(_otp_service)],
    sessions: Annotated[PatientSessionStore, Depends(_patient_sessions)],
) -> PatientOtpVerifyResponse:
    await service.verify(payload.link_token, payload.code)
    raw_session = await sessions.start(payload.link_token)
    _set_patient_session_cookie(response, raw_session)
    return PatientOtpVerifyResponse(session_expires_in_seconds=PATIENT_SESSION_SECONDS)


@patient_otp_router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_patient_session(
    response: Response,
    sessions: Annotated[PatientSessionStore, Depends(_patient_sessions)],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> Response:
    await sessions.revoke(patient_session)
    response.delete_cookie(
        key=PATIENT_SESSION_COOKIE_NAME,
        path="/api/v1",
        domain=config.COOKIE_DOMAIN or None,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
