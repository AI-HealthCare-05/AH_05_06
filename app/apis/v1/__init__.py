from fastapi import APIRouter

from app.apis.v1.auth_routers import auth_router
from app.apis.v1.health_routers import health_router
from app.apis.v1.patient_routers import patient_router
from app.apis.v1.user_routers import user_router
from app.apis.v1.visit_routers import visit_router

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(health_router)
v1_routers.include_router(auth_router)
v1_routers.include_router(user_router)
v1_routers.include_router(patient_router)
v1_routers.include_router(visit_router)
