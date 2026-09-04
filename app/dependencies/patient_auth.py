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

    require_patient_session과 독립적으로 실제 쿠키를 확인한다. require_patient_session이
    테스트에서 override로 우회되는 경우에도, 이 값은 override와 무관하게 실제 세션
    유무를 그대로 반영해야 patient_name 노출 여부가 정확하다 (KEY-178 리뷰로 발견).
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
