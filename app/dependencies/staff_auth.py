"""보호 API 의 문지기 — KEY-73 (`docs/auth-contract.md` 5절).

세 가지를 순서대로 본다.

    ① 서명·만료·**종류**   아니면 401 token_expired
    ② 로그아웃했거나 세션이 전부 끊겼는가   아니면 401 token_expired
    ③ 비밀번호를 바꿔야 하는가   그러면 403 password_change_required

①의 「종류」가 중요하다 — 이것이 없으면 리프레시 토큰을 Bearer 로 보내
액세스처럼 쓸 수 있다(`app/core/jwt/tokens.py`).

③의 예외는 **자기 자신을 벗어나지 않는 것뿐**이다 — `/auth/me` ·
`PATCH /auth/password` · `POST /auth/logout` 셋만 통과시킨다. 그 셋까지 막으면
비밀번호를 바꿀 방법이 없어 계정이 영영 잠긴다.

예외 목록을 여기 적어 두지 않는다. **경로가 스스로 표시를 달고**, 여기서는
그 표시만 읽는다 — 목록과 경로가 따로 놀면 어긋난 것을 아무도 모른다.

401 과 403 을 섞지 않는다. 화면이 「다시 로그인하세요」와 「권한이 없습니다」
중 무엇을 낼지 정하지 못한다.
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.core.auth_errors import PASSWORD_CHANGE_REQUIRED, TOKEN_EXPIRED, AuthError
from app.core.jwt.exceptions import TokenError
from app.core.jwt.tokens import AccessToken
from app.core.redis_client import get_redis
from app.models.staffs import Staff, StaffStatus
from app.services.session_store import SessionStore

# 헤더가 없을 때 FastAPI 가 403 을 내지 않도록 끈다.
# 인증이 아예 없는 것은 401 이다 — 로그인하면 되는 상황이기 때문이다.
bearer = HTTPBearer(auto_error=False)

#: 라우터가 `openapi_extra` 에 이 표시를 달아 두면 관문을 지난다.
#:
#: 예전에는 경로 문자열 목록을 여기 박아 두었다. 경로를 옮기거나 이름을 바꾸면
#: 이 목록만 옛것으로 남는데, 그러면 둘 중 하나가 된다 — 비밀번호를 바꿀 길이
#: 막혀 계정이 잠기거나, 반대로 관문이 뚫린다. 어느 쪽이든 조용히 일어난다.
#: 표시를 경로 옆에 두면 함께 움직인다.
PASSWORD_GATE_EXEMPT_KEY = "x-password-gate-exempt"


def _is_password_gate_exempt(request: Request) -> bool:
    route = request.scope.get("route")
    extra = getattr(route, "openapi_extra", None) or {}
    return bool(extra.get(PASSWORD_GATE_EXEMPT_KEY))


async def get_access_token(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AccessToken:
    if credential is None:
        raise AuthError(TOKEN_EXPIRED, 401, "로그인이 필요합니다.")

    try:
        token = AccessToken(token=credential.credentials)
    except TokenError as err:
        raise AuthError(TOKEN_EXPIRED, 401, "세션이 만료되었습니다. 다시 로그인해 주세요.") from err

    sessions = SessionStore(redis)

    jti = token.payload.get("jti")
    if jti and await sessions.is_access_revoked(jti):
        raise AuthError(TOKEN_EXPIRED, 401, "세션이 만료되었습니다. 다시 로그인해 주세요.")

    return token


async def get_current_staff(
    request: Request,
    token: Annotated[AccessToken, Depends(get_access_token)],
) -> Staff:
    staff_id = token.payload.get("staff_id")
    if not staff_id:
        # 옛 계약(user_id)으로 만든 토큰. 직원 API 는 받지 않는다.
        raise AuthError(TOKEN_EXPIRED, 401, "세션이 만료되었습니다. 다시 로그인해 주세요.")

    staff = await Staff.get_or_none(staff_id=int(staff_id))
    if staff is None or staff.status is not StaffStatus.ACTIVE:
        # 로그인한 뒤 그만둔 사람. 토큰이 안 만료됐어도 더는 못 들어온다.
        raise AuthError(TOKEN_EXPIRED, 401, "세션이 만료되었습니다. 다시 로그인해 주세요.")

    if staff.must_change_password and not _is_password_gate_exempt(request):
        raise AuthError(
            PASSWORD_CHANGE_REQUIRED,
            403,
            "비밀번호를 먼저 변경해 주세요.",
        )

    return staff
