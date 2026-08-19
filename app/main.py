from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.core.config import Config, Env
from app.core.db.databases import initialize_tortoise

_config = Config()
_is_prod = _config.ENV == Env.PROD

app = FastAPI(
    default_response_class=ORJSONResponse,
    docs_url=None if _is_prod else "/api/docs",
    redoc_url=None if _is_prod else "/api/redoc",
    openapi_url=None if _is_prod else "/api/openapi.json",
)
initialize_tortoise(app)

app.include_router(v1_routers)

# 로컬·개발 환경에서 Nginx 없이 프론트엔드를 직접 서빙한다.
# 프로덕션에서는 Nginx가 담당하므로 마운트하지 않는다.
if not _is_prod:
    _frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if _frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
