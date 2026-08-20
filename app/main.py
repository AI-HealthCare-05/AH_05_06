from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.apis.v1 import v1_routers
from app.core.auth_errors import AuthError, auth_error_handler
from app.core.config import Config, Env
from app.core.db.databases import initialize_tortoise
from app.core.error_handlers import register_error_handlers

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

# 인증 오류는 계약이 정한 코드 그대로 나간다 (KEY-73).
# 마스킹 뒤에 붙인다 — 이쪽이 더 좁은 예외라 먼저 잡혀야 하고,
# 본문에 담기는 것은 코드와 문구뿐이라 가릴 것이 없다.
app.add_exception_handler(AuthError, auth_error_handler)

app.include_router(v1_routers)
