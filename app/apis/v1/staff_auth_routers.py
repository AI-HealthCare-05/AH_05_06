"""직원 인증 — KEY-73 (`docs/auth-contract.md` 4절).

기존 `/auth/login` 은 `email` 로 받는 예시 골격이고 이 라우터가 계약본이다.
둘이 같은 경로를 쓸 수 없으므로 `auth_routers.py` 의 로그인은 걷어냈다.
`signup` 정리는 이 티켓 밖이다(계정 관리 · A1-2).
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from redis.asyncio import Redis

from app.core import config
from app.core.auth_errors import (
    RESPONSE_LOGIN_FAILURE,
    RESPONSE_PASSWORD_CHANGE_ERROR,
    RESPONSE_TOKEN_EXPIRED,
    TOKEN_EXPIRED,
    AuthError,
)
from app.core.config import Env
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.redis_client import get_redis
from app.dependencies.staff_auth import get_access_token, get_current_staff
from app.dtos.auth import (
    PasswordChangeRequest,
    StaffLoginRequest,
    StaffLoginResponse,
    StaffMeResponse,
    TokenRefreshResponse,
)
from app.models.staffs import Staff
from app.services.staff_auth import PasswordService, StaffAuthService, StaffSessionService

staff_auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 리프레시 토큰은 이 경로에만 실려 나간다. 화면을 그리는 요청마다 따라다니면
# 새어 나갈 자리만 늘어난다.
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_NAME = "refresh_token"

# 비밀번호를 바꾸기 전에도 지날 수 있는 길임을 **경로 자신이** 밝힌다.
# 예전에는 목록이 `dependencies/staff_auth.py` 에 문자열로 박혀 있었다 —
# 경로를 옮기거나 이름을 바꾸면 목록만 옛것으로 남아, 비밀번호를 못 바꾸는
# 계정이 생기거나(막혀서) 반대로 관문이 뚫린다.
PASSWORD_GATE_EXEMPT = {"x-password-gate-exempt": True}


def _auth(redis: Annotated[Redis, Depends(get_redis)]) -> StaffAuthService:
    return StaffAuthService(redis)


def _session(redis: Annotated[Redis, Depends(get_redis)]) -> StaffSessionService:
    return StaffSessionService(redis)


def _passwords(redis: Annotated[Redis, Depends(get_redis)]) -> PasswordService:
    return PasswordService(redis)


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


@staff_auth_router.post(
    "/login",
    response_model=StaffLoginResponse,
    status_code=status.HTTP_200_OK,
    responses=RESPONSE_LOGIN_FAILURE,
)
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


@staff_auth_router.post(
    "/refresh",
    response_model=TokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    responses=RESPONSE_TOKEN_EXPIRED,
)
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


@staff_auth_router.post(
    "/logout",
    openapi_extra=PASSWORD_GATE_EXEMPT,
    status_code=status.HTTP_204_NO_CONTENT,
    responses=RESPONSE_TOKEN_EXPIRED,
)
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


@staff_auth_router.get(
    "/me",
    openapi_extra=PASSWORD_GATE_EXEMPT,
    response_model=StaffMeResponse,
    status_code=status.HTTP_200_OK,
    responses=RESPONSE_TOKEN_EXPIRED,
)
async def me(staff: Annotated[Staff, Depends(get_current_staff)]) -> StaffMeResponse:
    """세션 복원과 화면 분기의 근거. 새로고침할 때마다 부른다."""
    await staff.fetch_related("hospital")
    return StaffMeResponse(
        id=staff.staff_id,
        name=staff.name,
        login_id=staff.login_id,
        roles=list(staff.roles or []),
        must_change_password=staff.must_change_password,
        clinic_name=staff.hospital.name,
    )


@staff_auth_router.patch(
    "/password",
    openapi_extra=PASSWORD_GATE_EXEMPT,
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**RESPONSE_TOKEN_EXPIRED, **RESPONSE_PASSWORD_CHANGE_ERROR},
)
async def change_password(
    body: PasswordChangeRequest,
    response: Response,
    staff: Annotated[Staff, Depends(get_current_staff)],
    passwords: Annotated[PasswordService, Depends(_passwords)],
) -> Response:
    """성공하면 기존 세션을 전부 폐기한다 — 자기 것까지.

    화면은 로그인으로 돌아가 새 비밀번호로 다시 들어온다. 쿠키를 남겨 두면
    죽은 토큰을 계속 들고 다니게 된다.
    """
    await passwords.change(staff, body.new_password, body.current_password)

    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        domain=config.COOKIE_DOMAIN or None,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
