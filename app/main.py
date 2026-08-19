from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

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
