"""오류 응답에서 민감정보를 걷어낸다 — KEY-11.

인수조건: 「예외 응답의 민감정보 제거」

로그는 우리만 보지만 **오류 응답은 사용자 브라우저·프록시·에러 추적 서비스에
그대로 남는다.** 로그보다 멀리 간다.

세 갈래를 막는다
--------------
**검증 오류(422)** — FastAPI 가 `input` 에 **사용자가 보낸 값을 그대로** 담는다.
비밀번호가 여덟 자 미만이면 그 비밀번호가 응답에 실려 나간다.

**`HTTPException` 의 `detail`** — 개발자가 쓴 문장이 그대로 나간다.
`detail=f"invalid token {token}"` 같은 코드는 언제든 생긴다.

**처리 안 된 예외(500)** — FastAPI 기본이 `Internal Server Error` 만 보낸다.
이미 안전해서 손대지 않는다.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.masking import scrub


async def masked_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """`input` 을 통째로 뺀다.

    사용자가 방금 보낸 값을 되돌려 줄 이유가 없다. **무엇이 잘못됐는지는
    `loc`(어느 필드)과 `msg`(무슨 규칙)로 충분히 알 수 있다.**

    필드 이름을 보고 가릴지 말지 고르지 않는다 — `password` 만 가리면
    `new_password` · `otp` · `token` 을 놓치고, 새 필드가 생길 때마다 또 놓친다.
    """
    cleaned: list[dict[str, Any]] = []
    for error in exc.errors():
        item = {k: v for k, v in error.items() if k != "input"}
        if isinstance(item.get("msg"), str):
            # 「value is not a valid email address: not-an-email」 처럼
            # msg 안에 값이 섞여 나오는 규칙도 있다.
            item["msg"] = scrub(item["msg"])
        # ctx 에는 예외 객체가 그대로 들어오기도 한다(`AfterValidator` 가 던진 ValueError).
        # 문자열로 바꿔 두지 않으면 직렬화가 실패해 **오류 응답 자체가 500이 된다.**
        if isinstance(item.get("ctx"), dict):
            item["ctx"] = {k: scrub(str(v)) for k, v in item["ctx"].items()}
        cleaned.append(item)
    return ORJSONResponse(status_code=422, content=jsonable_encoder({"detail": cleaned}))


async def masked_http_exception_handler(request: Request, exc: StarletteHTTPException) -> Any:
    """`detail` 을 훑고 나머지는 FastAPI 기본 동작에 맡긴다.

    직접 응답을 만들면 `WWW-Authenticate` 같은 헤더 처리를 다시 짜야 한다.
    """
    if isinstance(exc.detail, str):
        exc.detail = scrub(exc.detail)
    return await http_exception_handler(request, exc)


def register_error_handlers(app: FastAPI) -> None:
    """`app/main.py` 에서 한 줄로 붙인다 — 핸들러가 늘어도 main 은 안 커진다."""
    app.add_exception_handler(RequestValidationError, masked_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, masked_http_exception_handler)  # type: ignore[arg-type]
