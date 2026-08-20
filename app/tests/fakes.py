"""검사가 쓰는 가짜들 — KEY-73.

FakeRedis 를 파일마다 복사해 두었더니, 세션 저장소가 `setex` 를 쓰기 시작한
순간 한쪽만 조용히 깨졌다. 가짜도 한 군데 있어야 같이 자란다.
"""

from typing import Any, Self


class FakePipeline:
    """redis-py 의 파이프라인 흉내.

    진짜와 **호출 모양이 같아야** 한다 — 명령은 `await` 하지 않고 쌓기만 하고
    `execute()` 에서 한 번에 나간다. 여기서 `await` 를 붙여 두면 가짜만 통과하고
    실제 서버에서는 코루틴이 안 돌아 아무 일도 일어나지 않는다.
    """

    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.queued: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    def _queue(self, name: str, *args: Any) -> Self:
        self.queued.append((name, args))
        return self

    def setex(self, key: str, seconds: int, value: Any) -> Self:
        return self._queue("setex", key, seconds, value)

    def expire(self, key: str, seconds: int) -> Self:
        return self._queue("expire", key, seconds)

    def delete(self, key: str) -> Self:
        return self._queue("delete", key)

    def sadd(self, key: str, member: str) -> Self:
        return self._queue("sadd", key, member)

    def srem(self, key: str, member: str) -> Self:
        return self._queue("srem", key, member)

    async def execute(self) -> list[Any]:
        results = [await getattr(self.redis, name)(*args) for name, args in self.queued]
        self.queued.clear()
        return results


class FakeRedis:
    """세션 저장소가 쓰는 것만 흉내낸다.

    TTL 은 초를 세지 않는다 — 30분이 지났는지는 시계를 기다려서 볼 수 없으므로
    `expire()` 로 키를 지워 「유휴로 끊긴 상태」를 만든다.
    """

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}
        self.expire_calls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        value = self.values.get(key)
        return str(value) if value is not None else None

    async def setex(self, key: str, seconds: int, value: Any) -> None:
        self.values[key] = value
        self.ttls[key] = seconds

    async def exists(self, key: str) -> int:
        return 1 if key in self.values or key in self.sets else 0

    async def incr(self, key: str) -> int:
        self.values[key] = int(self.values.get(key, 0)) + 1
        return int(self.values[key])

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds
        self.expire_calls[key] = self.expire_calls.get(key, 0) + 1

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def delete(self, key: str) -> int:
        """지운 개수를 준다 — 진짜 Redis 와 같다.

        이 숫자가 「내가 이 토큰을 차지했다」의 근거가 된다. 없앤 값을 안
        돌려주면 확인과 삭제가 두 번으로 갈라져 동시 요청이 둘 다 통과한다.
        """
        found = key in self.values or key in self.sets
        self.values.pop(key, None)
        self.sets.pop(key, None)
        self.ttls.pop(key, None)
        return 1 if found else 0

    async def sadd(self, key: str, member: str) -> None:
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key: str, member: str) -> None:
        self.sets.get(key, set()).discard(member)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def pipeline(self, transaction: bool = False) -> FakePipeline:
        return FakePipeline(self)

    # ── 검사용 ──────────────────────────────────────────
    def idle_keys(self) -> list[str]:
        return [k for k in self.values if k.startswith("idle:")]

    def go_idle(self) -> None:
        """30분 가만히 있은 것으로 만든다 — TTL 로 사라진 것과 같은 상태."""
        for key in self.idle_keys():
            del self.values[key]


class InterleavingRedis(FakeRedis):
    """명령마다 이벤트 루프에 양보하는 가짜.

    `FakeRedis` 는 안에서 `await` 를 하지 않아, `asyncio.gather` 로 불러도
    각 호출이 **끝까지 붙어서** 돈다. 그러면 「보고 나서 없애는」 코드의 경합이
    재현되지 않아, 원자성 검사가 낡은 코드에서도 통과해 버린다.

    한 칸씩 양보하게 만들면 실제 서버에서 일어나는 끼어들기가 그대로 난다.
    """

    async def _yield(self) -> None:
        import asyncio

        await asyncio.sleep(0)

    async def get(self, key: str) -> str | None:
        await self._yield()
        return await super().get(key)

    async def exists(self, key: str) -> int:
        await self._yield()
        return await super().exists(key)

    async def incr(self, key: str) -> int:
        await self._yield()
        return await super().incr(key)

    async def delete(self, key: str) -> int:
        await self._yield()
        return await super().delete(key)

    async def setex(self, key: str, seconds: int, value: Any) -> None:
        await self._yield()
        await super().setex(key, seconds, value)
