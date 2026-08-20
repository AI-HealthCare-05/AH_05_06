from fastapi import APIRouter

from app.apis.v1.health_routers import health_router
from app.apis.v1.staff_auth_routers import staff_auth_router
from app.apis.v1.user_routers import user_router

# `auth_routers.py` 는 지웠다. 남아 있던 `POST /auth/signup` 은 email·password 로
# `User` 를 만드는데, 로그인은 이제 `login_id` 로 `Staff` 를 찾는다 — 그래서
# 이 경로로 만든 계정은 **영원히 로그인할 수 없는 죽은 데이터**였다.
# 직원 등록은 A1-2 에서 `Staff` 기준으로 새로 만든다.
# `AuthService` 자체는 `app/services/users.py` 가 쓰고 있어 그대로 둔다.

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(health_router)
v1_routers.include_router(staff_auth_router)
v1_routers.include_router(user_router)
