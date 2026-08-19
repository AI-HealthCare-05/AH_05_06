"""직원 로그인 — KEY-73 (`docs/auth-contract.md` 4절).

기존 `/auth/login` 은 `email` 로 받는 예시 골격이고 이 라우터가 계약본이다.
둘이 같은 경로를 쓸 수 없으므로 `auth_routers.py` 의 로그인은 걷어냈다.
`signup` 정리는 이 티켓 밖이다(계정 관리 · A1-2).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

from app.core import config
from app.core.config import Env
from app.core.redis_client import get_redis
from app.dtos.auth import StaffLoginRequest, StaffLoginResponse
from app.services.staff_auth import StaffAuthService

staff_auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 리프레시 토큰은 이 경로에만 실려 나간다. 화면을 그리는 요청마다 따라다니면
# 새어 나갈 자리만 늘어난다.
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_NAME = "refresh_token"


def _service(redis: Annotated[Redis, Depends(get_redis)]) -> StaffAuthService:
    return StaffAuthService(redis)


@staff_auth_router.post("/login", response_model=StaffLoginResponse, status_code=status.HTTP_200_OK)
async def login(
    body: StaffLoginRequest,
    response: Response,
    service: Annotated[StaffAuthService, Depends(_service)],
) -> StaffLoginResponse:
    staff, access, refresh = await service.login(body.login_id, body.password)

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=str(refresh),
        httponly=True,  # 스크립트가 못 읽는다 — XSS 로 새어도 훔쳐 갈 것이 없다
        secure=config.ENV == Env.PROD,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        domain=config.COOKIE_DOMAIN or None,
        # remember 는 발급 여부가 아니라 **쿠키가 얼마나 남는지**를 정한다.
        # 끄면 Max-Age 없는 세션 쿠키 — 브라우저를 닫으면 사라진다.
        # 켜도 유휴 30분은 그대로다(계약 4절) — 그건 refresh 쪽에서 본다.
        max_age=config.REFRESH_TOKEN_EXPIRE_MINUTES * 60 if body.remember else None,
    )

    return StaffLoginResponse(
        access_token=str(access),
        must_change_password=staff.must_change_password,
    )
