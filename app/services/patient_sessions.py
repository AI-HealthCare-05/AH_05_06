"""OTP 확인 뒤 발급하는 환자 전용 30분 세션 — KEY-92."""

import hashlib
import secrets

from redis.asyncio import Redis

from app.core.auth_errors import AuthError
from app.services.patient_links import digest_link_token

PATIENT_SESSION_SECONDS = 30 * 60


def digest_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _expired() -> AuthError:
    return AuthError("PATIENT_SESSION_EXPIRED", 401, "인증 시간이 만료되었습니다. 인증번호를 다시 확인해 주세요.")


class PatientSessionStore:
    """원문 세션 토큰은 쿠키에만 두고 Redis에는 digest만 저장한다.

    링크 하나에는 현재 세션 하나만 둔다. OTP를 다시 확인해 새 세션을 만들면
    이전 브라우저 세션은 즉시 폐기되어 새 접속이 기존 인증을 빌려 쓰지 못한다.
    """

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _session(session_digest: str) -> str:
        return f"patient_session:{session_digest}"

    @staticmethod
    def _current(link_digest: str) -> str:
        return f"patient_session_link:{link_digest}"

    async def start(self, raw_link_token: str) -> str:
        link_digest = digest_link_token(raw_link_token)
        current_key = self._current(link_digest)
        previous = await self.redis.get(current_key)
        raw_session = secrets.token_urlsafe(32)
        session_digest = digest_session_token(raw_session)

        async with self.redis.pipeline(transaction=False) as pipe:
            if previous:
                pipe.delete(self._session(previous))
            pipe.setex(self._session(session_digest), PATIENT_SESSION_SECONDS, link_digest)
            pipe.setex(current_key, PATIENT_SESSION_SECONDS, session_digest)
            await pipe.execute()
        return raw_session

    async def require(self, raw_session: str | None, raw_link_token: str) -> None:
        stored_link = await self.resolve_link_digest(raw_session)
        link_digest = digest_link_token(raw_link_token)
        if stored_link != link_digest:
            raise _expired()

    async def resolve_link_digest(self, raw_session: str | None) -> str:
        """Return the link digest owned by the current, non-rotated session."""

        if not raw_session:
            raise _expired()
        session_digest = digest_session_token(raw_session)
        link_digest = await self.redis.get(self._session(session_digest))
        if not link_digest:
            raise _expired()
        current_session = await self.redis.get(self._current(link_digest))
        if current_session != session_digest:
            raise _expired()
        return link_digest

    async def revoke(self, raw_session: str | None) -> None:
        if not raw_session:
            return
        session_digest = digest_session_token(raw_session)
        session_key = self._session(session_digest)
        link_digest = await self.redis.get(session_key)
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.delete(session_key)
            if link_digest:
                current_key = self._current(link_digest)
                if await self.redis.get(current_key) == session_digest:
                    pipe.delete(current_key)
            await pipe.execute()
