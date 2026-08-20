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
INVALID_REQUEST = "invalid_request"


def _example(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


# KEY-17 완료 조건 — "OpenAPI 에서 DTO 와 오류 예시 확인 가능".
# 성공 응답은 `response_model` 이 자동으로 채우지만, `AuthError` 는 커스텀
# 예외 핸들러로 나가서 `responses=` 로 직접 붙이지 않으면 문서에 안 뜬다.

RESPONSE_TOKEN_EXPIRED: dict[int | str, dict[str, Any]] = {
    401: {
        "description": "인증이 없거나, 만료·로그아웃·폐기된 토큰입니다. 다시 로그인해야 합니다.",
        "content": {
            "application/json": {"example": _example(TOKEN_EXPIRED, "세션이 만료되었습니다. 다시 로그인해 주세요.")}
        },
    }
}

RESPONSE_LOGIN_FAILURE: dict[int | str, dict[str, Any]] = {
    401: {
        "description": "아이디 또는 비밀번호가 올바르지 않습니다. 어느 쪽이 틀렸는지는 구분하지 않습니다.",
        "content": {
            "application/json": {
                "example": _example(
                    INVALID_CREDENTIALS,
                    "아이디 또는 비밀번호가 올바르지 않습니다.",
                    fail_count=2,
                    max_failures=5,
                )
            }
        },
    },
    429: {
        "description": "5회 이상 실패해 잠겼습니다.",
        "headers": {
            "Retry-After": {"schema": {"type": "integer"}, "description": "초 단위 재시도 대기 시간"},
        },
        "content": {
            "application/json": {
                "example": _example(
                    ACCOUNT_LOCKED,
                    "로그인 시도가 많아 잠시 잠겼습니다. 잠시 뒤 다시 시도해 주세요.",
                    retry_after_seconds=600,
                )
            }
        },
    },
}

RESPONSE_PASSWORD_CHANGE_ERROR: dict[int | str, dict[str, Any]] = {
    422: {
        "description": "현재 비밀번호가 빠졌거나 맞지 않거나, 새 비밀번호가 지금 것과 같습니다.",
        "content": {
            "application/json": {"example": _example(INVALID_REQUEST, "지금 쓰시는 비밀번호를 함께 입력해 주세요.")}
        },
    }
}
