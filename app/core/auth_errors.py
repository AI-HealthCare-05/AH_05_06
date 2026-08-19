"""인증 오류의 모양 — KEY-73.

계약(`docs/auth-contract.md` 5절)이 코드로 구분하라고 정한 이유는,
**같은 상태 코드라도 사용자가 해야 할 일이 다르기 때문**이다.

    401 invalid_credentials  다시 입력해야 한다
    401 token_expired        다시 로그인해야 한다

둘을 한 코드로 뭉치면 화면이 무슨 문구를 낼지 정하지 못한다.

본문을 평평하게 낸다. FastAPI 의 `HTTPException` 은 `{"detail": ...}` 로 감싸는데,
그러면 화면이 `data.code` 를 못 읽고 한 겹을 벗겨야 한다 — 계약에 없는 층이다.
"""

from typing import Any

from fastapi import Request
from fastapi.responses import ORJSONResponse


class AuthError(Exception):
    """계약이 정한 코드 그대로 나가는 오류."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.extra = extra or {}
        self.headers = headers or {}


async def auth_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
    assert isinstance(exc, AuthError)
    return ORJSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, **exc.extra},
        headers=exc.headers,
    )


INVALID_CREDENTIALS = "invalid_credentials"
ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
TOKEN_EXPIRED = "token_expired"
PASSWORD_CHANGE_REQUIRED = "password_change_required"
