"""Redis 연결 하나 — KEY-73.

로그인 실패 횟수와 세션 상태가 여기 얹힌다. 프로세스마다 풀 하나만 만든다.
"""

from redis.asyncio import Redis

from app.core import config

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
