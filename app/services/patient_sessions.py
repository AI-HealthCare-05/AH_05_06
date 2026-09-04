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

    async def _is_current(self, session_digest: str, link_digest: str) -> bool:
        """`session_digest` 가 이 링크에 지금 살아 있는 세션인지만 본다 — 예외 없음."""
        stored_link = await self.redis.get(self._session(session_digest))
        if stored_link != link_digest:
            return False
        current_session = await self.redis.get(self._current(link_digest))
        return current_session == session_digest

    async def check(self, raw_session: str | None, raw_link_token: str) -> int:
        """세션이 유효하면 남은 초를 반환하고, 만료·없음이면 PATIENT_SESSION_EXPIRED를 올린다."""
        if not raw_session:
            raise _expired()
        session_digest = digest_session_token(raw_session)
        link_digest = digest_link_token(raw_link_token)
        if not await self._is_current(session_digest, link_digest):
            raise _expired()
        ttl: int = await self.redis.ttl(self._session(session_digest))
        return max(0, ttl)

    async def has_valid_session(self, raw_session: str | None, raw_link_token: str) -> bool:
        """세션이 이 링크에 유효한지 여부만 돌려준다 — 없거나 만료여도 예외를 올리지 않는다.

        `require`·`check` 는 관문이지만 이것은 「인증했는가」 표시용이다. 환자명처럼
        인증한 뷰어에게만 보태는 필드를 켤지 정하는 데만 쓴다 (KEY-268).
        """
        if not raw_session:
            return False
        session_digest = digest_session_token(raw_session)
        link_digest = digest_link_token(raw_link_token)
        return await self._is_current(session_digest, link_digest)

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
