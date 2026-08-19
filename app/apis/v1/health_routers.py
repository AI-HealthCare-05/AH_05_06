from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis
from tortoise import Tortoise

from app.core import config

health_router = APIRouter(prefix="/health", tags=["health"])


async def _check_db() -> dict:
    try:
        conn = Tortoise.get_connection("default")
        await conn.execute_query("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_redis() -> dict:
    try:
        client = Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


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
