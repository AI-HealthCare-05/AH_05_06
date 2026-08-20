from collections.abc import Awaitable
from typing import cast

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis
from tortoise import Tortoise

from app.core import config
from app.core.config import Env
from app.core.logger import setup_logger

health_router = APIRouter(prefix="/health", tags=["health"])

logger = setup_logger("health")


async def _check_db() -> dict:
    try:
        conn = Tortoise.get_connection("default")
        await conn.execute_query("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        logger.warning("health: db check failed", exc_info=e)
        result: dict = {"status": "error", "reason": "connection_failed"}
        if config.ENV == Env.LOCAL:
            result["detail"] = str(e)
        return result


async def _check_redis() -> dict:
    try:
        client = Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, socket_connect_timeout=2)
        # redis-py 의 ping() 은 동기·비동기 두 반환을 겹쳐 선언해 두어 그대로 await 하면
        # 타입이 안 맞는다. 실행은 되지만 검사에 걸리므로 비동기 쪽임을 밝혀 준다.
        await cast(Awaitable[bool], client.ping())
        await client.aclose()
        return {"status": "ok"}
    except Exception as e:
        logger.warning("health: redis check failed", exc_info=e)
        result: dict = {"status": "error", "reason": "connection_failed"}
        if config.ENV == Env.LOCAL:
            result["detail"] = str(e)
        return result


@health_router.get("", summary="헬스체크")
async def health_check() -> ORJSONResponse:
    db_result = await _check_db()
    redis_result = await _check_redis()

    services = {
        "api": {"status": "ok"},
        "db": db_result,
        "redis": redis_result,
    }

    all_ok = all(s["status"] == "ok" for s in services.values())
    http_status = 200 if all_ok else 503

    return ORJSONResponse(
        content={"status": "ok" if all_ok else "degraded", "services": services},
        status_code=http_status,
    )
