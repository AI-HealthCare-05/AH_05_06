"""
[KEY-19] 로컬 환경 기동·헬스체크 스모크 테스트

DB와 Redis를 mock하여 CI 환경에서도 항상 실행 가능하다.
실제 기동 상태를 확인할 때는 docs/local-health-check.md 절차를 따른다.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette import status

from app.main import app

HEALTH_URL = "/api/v1/health"


@pytest.mark.asyncio
async def test_health_all_ok():
    """API·DB·Redis 모두 정상일 때 200과 ok 상태를 반환한다."""
    with (
        patch("app.apis.v1.health_routers._check_db", new=AsyncMock(return_value={"status": "ok"})),
        patch("app.apis.v1.health_routers._check_redis", new=AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(HEALTH_URL)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "ok"
    assert body["services"]["api"]["status"] == "ok"
    assert body["services"]["db"]["status"] == "ok"
    assert body["services"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_db_down():
    """DB 연결 실패 시 503과 degraded 상태를 반환하고 db.error 필드가 존재한다."""
    with (
        patch(
            "app.apis.v1.health_routers._check_db",
            new=AsyncMock(return_value={"status": "error", "error": "Connection refused"}),
        ),
        patch("app.apis.v1.health_routers._check_redis", new=AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(HEALTH_URL)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["db"]["status"] == "error"
    assert "error" in body["services"]["db"]


@pytest.mark.asyncio
async def test_health_redis_down():
    """Redis 연결 실패 시 503과 degraded 상태를 반환하고 redis.error 필드가 존재한다."""
    with (
        patch("app.apis.v1.health_routers._check_db", new=AsyncMock(return_value={"status": "ok"})),
        patch(
            "app.apis.v1.health_routers._check_redis",
            new=AsyncMock(return_value={"status": "error", "error": "Connection refused"}),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(HEALTH_URL)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["redis"]["status"] == "error"
    assert "error" in body["services"]["redis"]


@pytest.mark.asyncio
async def test_health_response_structure():
    """응답 구조에 status와 services(api·db·redis) 키가 항상 존재한다."""
    with (
        patch("app.apis.v1.health_routers._check_db", new=AsyncMock(return_value={"status": "ok"})),
        patch("app.apis.v1.health_routers._check_redis", new=AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(HEALTH_URL)

    body = response.json()
    assert "status" in body
    assert "services" in body
    for service in ("api", "db", "redis"):
        assert service in body["services"], f"services.{service} 키 누락"
        assert "status" in body["services"][service], f"services.{service}.status 키 누락"
