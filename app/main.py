from fastapi import FastAPI
from fastapi.responses import JSONResponse, ORJSONResponse

from app.apis.v1 import v1_routers
from app.core.auth_errors import AuthError, auth_error_handler
from app.core.config import Config, Env
from app.core.db.databases import initialize_tortoise
from app.core.error_handlers import register_error_handlers
from app.core.logger import mask_server_logs
from app.core.masking import scrub
from app.ocr.errors import OcrApiError

_config = Config()
_is_prod = _config.ENV == Env.PROD

# uvicorn 의 access 로그에도 가리개를 붙인다 (KEY-155).
#
# **앱을 만들기 전에 부른다.** uvicorn 은 자기 로깅 설정을 먼저 끝내고 그다음
# 이 모듈을 임포트하므로, 여기서 붙이면 첫 요청 전에 걸린다.
mask_server_logs()

app = FastAPI(
    default_response_class=ORJSONResponse,
    docs_url=None if _is_prod else "/api/docs",
    redoc_url=None if _is_prod else "/api/redoc",
    openapi_url=None if _is_prod else "/api/openapi.json",
)
initialize_tortoise(app)

# 오류 응답에서 민감정보를 걷어낸다 (KEY-11) — 로그보다 멀리 가는 경로다
register_error_handlers(app)

# 인증 오류는 계약이 정한 코드 그대로 나간다 (KEY-73).
# 마스킹 뒤에 붙인다 — 이쪽이 더 좁은 예외라 먼저 잡혀야 하고,
# 본문에 담기는 것은 코드와 문구뿐이라 가릴 것이 없다.
app.add_exception_handler(AuthError, auth_error_handler)

app.include_router(v1_routers)


@app.exception_handler(OcrApiError)
async def ocr_api_error_handler(_, exc: OcrApiError) -> JSONResponse:
    # 다른 예외는 register_error_handlers()가 scrub() 한다 (KEY-11).
    # 이 핸들러는 그 경로를 안 거치므로 여기서 직접 가린다 — 지금은 모든
    # OcrApiError.message 가 고정 문구지만, 벤더 원문을 그대로 실어 던지는
    # 코드가 나중에 생겨도 이 자리에서 걸리게 해 둔다 (KEY-48).
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": scrub(exc.message), "field_errors": None},
    )
