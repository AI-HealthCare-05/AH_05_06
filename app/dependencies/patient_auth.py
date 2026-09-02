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


async def require_patient_feedback_session(
    redis: Annotated[Redis, Depends(get_redis)],
    patient_session: Annotated[str | None, Cookie(alias=PATIENT_SESSION_COOKIE_NAME)] = None,
) -> str:
    """Resolve feedback scope from the HttpOnly session without accepting a link token."""

    return await PatientSessionStore(redis).resolve_link_digest(patient_session)
