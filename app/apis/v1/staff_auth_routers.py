"""직원 인증 — KEY-73 (`docs/auth-contract.md` 4절).

기존 `/auth/login` 은 `email` 로 받는 예시 골격이고 이 라우터가 계약본이다.
둘이 같은 경로를 쓸 수 없으므로 `auth_routers.py` 의 로그인은 걷어냈다.
`signup` 정리는 이 티켓 밖이다(계정 관리 · A1-2).
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from redis.asyncio import Redis

from app.core import config
from app.core.auth_errors import TOKEN_EXPIRED, AuthError
from app.core.config import Env
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.redis_client import get_redis
from app.dependencies.staff_auth import get_access_token, get_current_staff
from app.dtos.auth import StaffLoginRequest, StaffLoginResponse, TokenRefreshResponse
from app.models.staffs import Staff
from app.services.staff_auth import StaffAuthService, StaffSessionService

staff_auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 리프레시 토큰은 이 경로에만 실려 나간다. 화면을 그리는 요청마다 따라다니면
# 새어 나갈 자리만 늘어난다.
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_NAME = "refresh_token"


def _auth(redis: Annotated[Redis, Depends(get_redis)]) -> StaffAuthService:
    return StaffAuthService(redis)


def _session(redis: Annotated[Redis, Depends(get_redis)]) -> StaffSessionService:
    return StaffSessionService(redis)


def _set_refresh_cookie(response: Response, refresh: RefreshToken) -> None:
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
        # 켜도 유휴 30분은 그대로다 — 그건 refresh 가 본다.
        max_age=config.REFRESH_TOKEN_EXPIRE_MINUTES * 60 if refresh.payload.get("remember") else None,
    )


@staff_auth_router.post("/login", response_model=StaffLoginResponse, status_code=status.HTTP_200_OK)
async def login(
    body: StaffLoginRequest,
    response: Response,
    auth: Annotated[StaffAuthService, Depends(_auth)],
    session: Annotated[StaffSessionService, Depends(_session)],
) -> StaffLoginResponse:
    staff = await auth.login(body.login_id, body.password)
    access, refresh = await session.start(staff, body.remember)
    _set_refresh_cookie(response, refresh)

    return StaffLoginResponse(
        access_token=str(access),
        must_change_password=staff.must_change_password,
    )


@staff_auth_router.post("/refresh", response_model=TokenRefreshResponse, status_code=status.HTTP_200_OK)
async def refresh(
    response: Response,
    session: Annotated[StaffSessionService, Depends(_session)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenRefreshResponse:
    """요청 본문이 없다. 쿠키로 온 리프레시 토큰만 본다."""
    if not refresh_token:
        # 쿠키가 없으면 세션이 없는 것과 같다. 「인증정보가 틀렸다」가 아니다.
        raise AuthError(TOKEN_EXPIRED, 401, "세션이 만료되었습니다. 다시 로그인해 주세요.")

    _, access, rotated = await session.rotate(refresh_token)
    _set_refresh_cookie(response, rotated)
    return TokenRefreshResponse(access_token=str(access))


@staff_auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: Annotated[StaffSessionService, Depends(_session)],
    staff: Annotated[Staff, Depends(get_current_staff)],
    token: Annotated[AccessToken, Depends(get_access_token)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    """액세스와 리프레시를 함께 무효로 만들고 쿠키를 지운다.

    `get_current_staff` 도 같은 의존성을 거치므로 토큰은 한 번만 검증된다.
    """
    await session.logout(refresh_token, token.payload.get("jti"), staff.staff_id)

    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        domain=config.COOKIE_DOMAIN or None,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
