"""검사가 쓰는 가짜들 — KEY-73.

FakeRedis 를 파일마다 복사해 두었더니, 세션 저장소가 `setex` 를 쓰기 시작한
순간 한쪽만 조용히 깨졌다. 가짜도 한 군데 있어야 같이 자란다.
"""

from typing import Any


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

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.sets.pop(key, None)
        self.ttls.pop(key, None)

    async def sadd(self, key: str, member: str) -> None:
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key: str, member: str) -> None:
        self.sets.get(key, set()).discard(member)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    # ── 검사용 ──────────────────────────────────────────
    def idle_keys(self) -> list[str]:
        return [k for k in self.values if k.startswith("idle:")]

    def go_idle(self) -> None:
        """30분 가만히 있은 것으로 만든다 — TTL 로 사라진 것과 같은 상태."""
        for key in self.idle_keys():
            del self.values[key]
