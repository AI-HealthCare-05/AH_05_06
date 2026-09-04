"""환자용 안내·D+7 API의 세션 관문 — KEY-92."""

from typing import Annotated

from fastapi import Cookie, Depends
from redis.asyncio import Redis

from app.core.redis_client import get_redis
from app.services.patient_sessions import PatientSessionStore

PATIENT_SESSION_COOKIE_NAME = "patient_session"


async def require_patient_session(
    token: str,
    redis: Annotated[Redis, Depends(get_redis)],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> None:
    await PatientSessionStore(redis).require(patient_session, token)


async def optional_patient_session(
    token: str,
    redis: Annotated[Redis, Depends(get_redis)],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> bool:
    """OTP 인증 세션이 이 링크에 유효한지 여부. 없거나 만료여도 막지 않는다 — KEY-268.

    안내 조회 자체는 링크 토큰만으로 열리고(KEY-178), 이 값은 환자명처럼 인증한
    뷰어에게만 보태는 필드를 켤지 정하는 데만 쓴다.
    """
    return await PatientSessionStore(redis).has_valid_session(patient_session, token)


async def require_patient_session_link(
    redis: Annotated[Redis, Depends(get_redis)],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> str:
    """Resolve the guide link digest from the HttpOnly patient session."""

    return await PatientSessionStore(redis).resolve_link_digest(patient_session)


# Keep the KEY-239 dependency name for existing feedback routes.
require_patient_feedback_session = require_patient_session_link
