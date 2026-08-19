from fastapi import FastAPI
from fastapi.responses import JSONResponse, ORJSONResponse

from app.apis.v1 import v1_routers
from app.core.config import Config, Env
from app.core.db.databases import initialize_tortoise
from app.core.error_handlers import register_error_handlers
from app.ocr.errors import OcrApiError

_config = Config()
_is_prod = _config.ENV == Env.PROD

app = FastAPI(
    default_response_class=ORJSONResponse,
    docs_url=None if _is_prod else "/api/docs",
    redoc_url=None if _is_prod else "/api/redoc",
    openapi_url=None if _is_prod else "/api/openapi.json",
)
initialize_tortoise(app)

# 오류 응답에서 민감정보를 걷어낸다 (KEY-11) — 로그보다 멀리 가는 경로다
register_error_handlers(app)

app.include_router(v1_routers)


@app.exception_handler(OcrApiError)
async def ocr_api_error_handler(_, exc: OcrApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "field_errors": None},
    )
