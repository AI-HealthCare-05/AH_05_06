"""환자 링크 OTP·인증·세션·재발급 API — KEY-91, KEY-219."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from redis.asyncio import Redis

from app.core import config
from app.core.config import Env, SmsProvider, otp_solapi_prod_gate_open, pilot_mock_otp_gate_open
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
    PatientSessionCheckRequest,
    PatientSessionResponse,
)
from app.services.patient_links import PatientLinkService
from app.services.patient_otp import (
    OTP_RESEND_COOLDOWN,
    ApprovedPhonesOnlyDelivery,
    MockOtpDelivery,
    OtpDelivery,
    PatientOtpService,
    SolapiOtpDelivery,
    UnavailableOtpDelivery,
)
from app.services.patient_sessions import PATIENT_SESSION_SECONDS, PatientSessionStore
from app.services.sms_sender import build_sms_sender

patient_auth_router = APIRouter(prefix="/patient-auth", tags=["patient-auth"])
patient_otp_router = APIRouter(prefix="/patient-auth/otp", tags=["patient-auth"])


def _approved_test_phones() -> frozenset[str]:
    raw = config.OTP_APPROVED_TEST_PHONES.get_secret_value()
    return frozenset(phone.strip() for phone in raw.split(",") if phone.strip())


def _otp_service() -> PatientOtpService:
    # prod에서는 KEY-264 좁은문이 열렸을 때만 고정 OTP를 허용한다.
    prod_allowed = config.ENV is not Env.PROD or pilot_mock_otp_gate_open()
    if config.MOCK_OTP_CODE and prod_allowed:
        return PatientOtpService(
            MockOtpDelivery(),
            fixed_otp_code=config.MOCK_OTP_CODE,
        )

    if config.SMS_PROVIDER is SmsProvider.SOLAPI:
        # prod에서 실제 발송을 켜려면 KEY-6 승인 뒤 넣는 이 좁은문이 따로
        # 필요하다 — SMS_PROVIDER=solapi와 자격증명만으로 켜지지 않는다.
        if config.ENV is Env.PROD and not otp_solapi_prod_gate_open():
            return PatientOtpService(UnavailableOtpDelivery())

        # 승인된 테스트 번호로만 실제 발송을 좁힌다 — KEY-284 검증 단계
        # 안전장치. **환경으로 갈라 두지 않는다** — Pilot도 ENV=prod로
        # 뜬다(KEY-264). "ENV가 prod가 아닐 때만" 이라고 두면, Pilot에서
        # 좁은문이 열리는 순간 이 래퍼가 통째로 빠져 임의 번호로 나간다
        # (yugaeun821 리뷰). 실제 운영 활성화(KEY-6)는 이 티켓 범위 밖이라,
        # 그 승인 절차가 생기기 전까지는 이 경로에 도달하는 모든 실행이
        # "검증 단계"다 — 항상 승인 번호로 좁힌다.
        delivery: OtpDelivery = ApprovedPhonesOnlyDelivery(
            SolapiOtpDelivery(build_sms_sender(config)),
            _approved_test_phones(),
        )
        return PatientOtpService(delivery)

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


@patient_auth_router.post("/session", response_model=PatientSessionResponse)
async def check_patient_session(
    payload: PatientSessionCheckRequest,
    sessions: Annotated[PatientSessionStore, Depends(_patient_sessions)],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> PatientSessionResponse:
    """**주소에 토큰을 안 싣는다** — KEY-292 (유가은 님 `#255` 리뷰).

    여기는 `GET …/session?link_token=<원문>` 이었다. `#255` 가 화면에서 조각
    토큰을 읽게 고치기 전에는 실서버가 이 자리에 **도달하지 못했는데**, 그
    고침이 길을 여는 순간 정상 진입마다 이 요청이 나가고 토큰이 nginx access
    log 에 원문으로 남는다. 그래서 후속으로 미루지 않고 같은 PR 에서 걷는다.
    """
    expires_in = await sessions.check(patient_session, payload.link_token)
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
