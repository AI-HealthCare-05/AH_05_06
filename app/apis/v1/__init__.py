from fastapi import APIRouter

from app.apis.v1.auth_routers import auth_router
from app.apis.v1.health_routers import health_router
from app.apis.v1.user_routers import user_router
from app.core.config import Config, Env

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(health_router)
v1_routers.include_router(auth_router)
v1_routers.include_router(user_router)

if Config().ENV != Env.PROD:
    from app.apis.v1.dev_ocr_router import dev_ocr_router

    v1_routers.include_router(dev_ocr_router)
