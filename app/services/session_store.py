"""세션 상태 — KEY-73 (`docs/auth-contract.md` 4·5절).

리프레시 토큰은 JWT 라 서명만 보면 만료 전까지 늘 유효하다. 그런데 계약은
세 가지를 더 요구한다.

    유휴 30분      가만히 있으면 끊긴다
    Rotation       쓴 토큰은 즉시 폐기하고 새것을 준다
    재사용 감지    폐기된 토큰이 다시 오면 훔친 것이 쓰였다는 뜻이다

셋 다 「이 토큰이 지금 살아 있는가」를 서명 밖에서 알아야 해서 Redis 가 필요하다.

키 셋이 각각 다른 질문에 답한다.

    idle:{jti}              살아 있는가 · 최근 활동이 있었는가   TTL 30분
    used:{jti}              이미 쓰인 토큰인가                   TTL 리프레시 수명
    sessions:{staff_id}        이 사람의 리프레시 세션 목록      전부 끊을 때 쓴다
    access_sessions:{staff_id} 이 사람의 살아 있는 액세스 jti     전부 끊을 때 쓴다

`used:` 를 따로 두는 이유가 중요하다. `idle:` 만 두면 **유휴로 끊긴 토큰**과
**훔쳐서 재사용된 토큰**이 똑같이 「키가 없음」으로 보인다. 앞은 그 토큰만
폐기하면 되지만 뒤는 **그 계정의 세션을 전부 끊어야 한다.** 둘을 못 가르면
도난을 조용히 넘긴다.
"""

from redis.asyncio import Redis

from app.core import config

IDLE_SECONDS = 30 * 60
REFRESH_SECONDS = config.REFRESH_TOKEN_EXPIRE_MINUTES * 60
ACCESS_SECONDS = config.ACCESS_TOKEN_EXPIRE_MINUTES * 60


class SessionStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    # ── 키 ──────────────────────────────────────────────
    @staticmethod
    def _idle(jti: str) -> str:
        return f"idle:{jti}"

    @staticmethod
    def _used(jti: str) -> str:
        return f"used:{jti}"

    @staticmethod
    def _sessions(staff_id: int) -> str:
        return f"sessions:{staff_id}"

    @staticmethod
    def _revoked_access(jti: str) -> str:
        return f"revoked_access:{jti}"

    @staticmethod
    def _access_sessions(staff_id: int) -> str:
        return f"access_sessions:{staff_id}"

    # ── 세션 ────────────────────────────────────────────
    async def open(self, jti: str, staff_id: int) -> None:
        """로그인 · rotation 성공 자리. 유휴 시계를 30분으로 되감는다.

        셋을 한 번에 보낸다. 따로 보내면 접수대에서 자주 도는 refresh 경로가
        왕복 수만큼 느려진다 — 서로 기다릴 이유가 없는 명령들이다.
        """
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.setex(self._idle(jti), IDLE_SECONDS, staff_id)
            pipe.sadd(self._sessions(staff_id), jti)
            # 세션 묶음이 영원히 남지 않게. 가장 오래 살 수 있는 토큰만큼만 둔다.
            pipe.expire(self._sessions(staff_id), REFRESH_SECONDS)
            await pipe.execute()

    async def is_alive(self, jti: str) -> bool:
        return await self.redis.exists(self._idle(jti)) == 1  # type: ignore[misc]

    async def was_used(self, jti: str) -> bool:
        return await self.redis.exists(self._used(jti)) == 1  # type: ignore[misc]

    async def retire(self, jti: str, staff_id: int) -> None:
        """이 토큰 하나를 폐기한다.

        `used:` 를 남기는 것이 핵심이다 — 나중에 같은 토큰이 오면 그것이
        **도난**인지 그냥 만료인지 여기서 갈린다.
        """
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.delete(self._idle(jti))
            pipe.setex(self._used(jti), REFRESH_SECONDS, 1)
            pipe.srem(self._sessions(staff_id), jti)
            await pipe.execute()

    async def claim(self, jti: str, staff_id: int) -> bool:
        """이 리프레시 토큰을 **내가** 차지한다. 차지했으면 True.

        예전에는 `was_used()` · `is_alive()` 로 보고 나서 `retire()` 했다.
        보는 것과 없애는 것이 갈라져 있으면, 같은 토큰으로 거의 동시에 두
        요청이 오면 **둘 다 「아직 안 쓰였다」를 보고 통과한다** — 훔친 토큰과
        정상 클라이언트가 겹칠 때가 정확히 그 경우다.

        `DELETE` 는 없앤 개수를 돌려주는 원자적 명령이다. 1 을 받은 쪽만
        그 토큰의 주인이 된다. 진 쪽은 0 을 받고, `used:` 를 보고 도난인지
        유휴 만료인지 가린다.
        """
        deleted = await self.redis.delete(self._idle(jti))
        if not deleted:
            return False
        # 이긴 즉시 「썼음」을 남긴다 — 진 쪽이 이것을 보고 도난을 알아챈다.
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.setex(self._used(jti), REFRESH_SECONDS, 1)
            pipe.srem(self._sessions(staff_id), jti)
            await pipe.execute()
        return True

    async def revoke_all(self, staff_id: int) -> int:
        """이 사람의 세션을 전부 끊는다.

        훔친 토큰이 쓰였을 때, 그리고 비밀번호를 바꿨을 때 부른다.
        비밀번호를 바꾸는 이유가 「남이 알고 있다」이므로 그 남의 세션도
        같이 끊어야 한다.

        **액세스 토큰도 함께 끊는다.** `sessions:` 에는 리프레시 jti 만 들어
        있어서 예전에는 이 함수가 리프레시만 죽였다. 그러면 비밀번호를 바꾸거나
        도난이 감지돼도 **이미 발급된 액세스 토큰이 최대 60분 더 살아 있다** —
        훔친 쪽이 그동안 계속 들어올 수 있다.

        발급 시각(`iat`)으로 「이 시각 이전 것은 무효」라고 끊는 방법도 있는데,
        `iat` 는 **초 단위**라 비밀번호를 바꾼 같은 초에 벌어진 일을 가르지
        못한다. 그래서 액세스도 리프레시처럼 jti 를 들고 있다가 하나씩 끊는다.
        수명이 60분이라 목록이 오래 자라지 않는다.
        """
        key = self._sessions(staff_id)
        jtis: set[str] = await self.redis.smembers(key)  # type: ignore[misc]
        for jti in jtis:
            await self.redis.delete(self._idle(jti))
            await self.redis.setex(self._used(jti), REFRESH_SECONDS, 1)
        await self.redis.delete(key)

        access_key = self._access_sessions(staff_id)
        access_jtis: set[str] = await self.redis.smembers(access_key)  # type: ignore[misc]
        for jti in access_jtis:
            await self.redis.setex(self._revoked_access(jti), ACCESS_SECONDS, 1)
        await self.redis.delete(access_key)

        return len(jtis)

    # ── 액세스 토큰 ─────────────────────────────────────
    async def track_access(self, jti: str, staff_id: int) -> None:
        """발급한 액세스 토큰을 기억해 둔다.

        `revoke_all` 이 이 목록을 보고 하나씩 끊는다. 기억해 두지 않으면
        리프레시만 죽고 **이미 발급된 액세스는 남은 수명만큼 계속 산다.**
        """
        await self.redis.sadd(self._access_sessions(staff_id), jti)  # type: ignore[misc]
        await self.redis.expire(self._access_sessions(staff_id), ACCESS_SECONDS)

    async def revoke_access(self, jti: str) -> None:
        """로그아웃한 액세스 토큰을 못 쓰게 한다.

        액세스 토큰은 서명만으로 도는 것이 원칙이지만, 「로그아웃 뒤 보호 API 에
        접근할 수 없다」는 계약이라 이것만은 매 요청 확인한다. 남은 수명만큼만
        들고 있으면 되므로 목록이 무한히 자라지 않는다.
        """
        await self.redis.setex(self._revoked_access(jti), ACCESS_SECONDS, 1)

    async def is_access_revoked(self, jti: str) -> bool:
        return await self.redis.exists(self._revoked_access(jti)) == 1  # type: ignore[misc]
