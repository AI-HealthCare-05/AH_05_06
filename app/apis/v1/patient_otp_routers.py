"""환자 링크 OTP·인증·세션·재발급 API — KEY-91, KEY-219."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Response, status
from redis.asyncio import Redis

from app.core import config
from app.core.config import Env
from app.core.redis_client import get_redis
from app.dependencies.patient_auth import PATIENT_SESSION_COOKIE_NAME
from app.dtos.patient_otp import (
    PatientAuthContextRequest,
    PatientAuthContextResponse,
    PatientLinkReIssueRequest,
    PatientLinkReIssueResponse,
    PatientOtpIssueRequest,
    PatientOtpIssueResponse,
    PatientOtpVerifyRequest,
    PatientOtpVerifyResponse,
    PatientSessionResponse,
)
from app.services.patient_links import PatientLinkService
from app.services.patient_otp import (
    OTP_RESEND_COOLDOWN,
    MockOtpDelivery,
    PatientOtpService,
    UnavailableOtpDelivery,
)
from app.services.patient_sessions import PATIENT_SESSION_SECONDS, PatientSessionStore

patient_auth_router = APIRouter(prefix="/patient-auth", tags=["patient-auth"])
patient_otp_router = APIRouter(prefix="/patient-auth/otp", tags=["patient-auth"])


def _otp_service() -> PatientOtpService:
    if config.ENV is not Env.PROD and config.MOCK_OTP_CODE:
        return PatientOtpService(
            MockOtpDelivery(),
            fixed_otp_code=config.MOCK_OTP_CODE,
        )
    return PatientOtpService(UnavailableOtpDelivery())


def _patient_sessions(redis: Annotated[Redis, Depends(get_redis)]) -> PatientSessionStore:
    return PatientSessionStore(redis)


def _link_service() -> PatientLinkService:
    return PatientLinkService()


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


@patient_auth_router.post("/context", response_model=PatientAuthContextResponse)
async def get_patient_auth_context(
    payload: PatientAuthContextRequest,
    service: Annotated[PatientLinkService, Depends(_link_service)],
) -> PatientAuthContextResponse:
    ctx = await service.get_context(payload.link_token)
    return PatientAuthContextResponse(
        hospital_name=ctx.hospital_name,
        masked_phone=ctx.masked_phone,
        visited_at=ctx.visited_at,
        expires_at=ctx.expires_at,
    )


@patient_auth_router.get("/session", response_model=PatientSessionResponse)
async def check_patient_session(
    sessions: Annotated[PatientSessionStore, Depends(_patient_sessions)],
    link_token: Annotated[str, Query()],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> PatientSessionResponse:
    expires_in = await sessions.check(patient_session, link_token)
    return PatientSessionResponse(expires_in_seconds=expires_in)


@patient_auth_router.post(
    "/link/re-issue",
    response_model=PatientLinkReIssueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def re_issue_patient_link(
    payload: PatientLinkReIssueRequest,
    service: Annotated[PatientLinkService, Depends(_link_service)],
) -> PatientLinkReIssueResponse:
    await service.re_issue(payload.link_token)
    return PatientLinkReIssueResponse()


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
