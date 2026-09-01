from fastapi import APIRouter

from app.apis.v1.chatbot_routers import chatbot_router
from app.apis.v1.front_desk_routers import front_desk_router
from app.apis.v1.guide_copy_routers import guide_copy_router
from app.apis.v1.guide_routers import guide_router
from app.apis.v1.health_routers import health_router
from app.apis.v1.lab_baseline_routers import lab_baseline_router
from app.apis.v1.message_routers import message_router
from app.apis.v1.message_template_routers import message_template_router
from app.apis.v1.patient_link_routers import (
    patient_checkin_router,
    patient_guide_router,
    patient_link_management_router,
)
from app.apis.v1.patient_otp_routers import patient_otp_router
from app.apis.v1.patient_routers import patient_router
from app.apis.v1.staff_auth_routers import staff_auth_router
from app.apis.v1.visit_routers import visit_router
from app.catalog.api import catalog_router
from app.documents.api import document_router
from app.ocr.api import ocr_router
from app.timeline.api import timeline_router

# `auth_routers.py` 는 지웠다. 남아 있던 `POST /auth/signup` 은 email·password 로
# `User` 를 만드는데, 로그인은 이제 `login_id` 로 `Staff` 를 찾는다 — 그래서
# 이 경로로 만든 계정은 **영원히 로그인할 수 없는 죽은 데이터**였다.
# 직원 등록은 A1-2 에서 `Staff` 기준으로 새로 만든다.
#
# `user_routers.py` 도 같은 이유로 지웠다(KEY-167). `GET·PATCH /users/me` 는
# `get_request_user` 로 `users` 표를 읽는데, 그 표를 채우는 경로가 없어져서
# **아무도 부를 수 없는 API** 였다. 화면도 `/auth/me` 만 쓴다.
# `app/models/users.py` 의 `User` 모델과 JWT 경로는 이 일감 범위 밖이라 남긴다.

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(health_router)
v1_routers.include_router(staff_auth_router)
v1_routers.include_router(patient_router)
v1_routers.include_router(visit_router)
v1_routers.include_router(front_desk_router)
v1_routers.include_router(catalog_router)
v1_routers.include_router(document_router)
v1_routers.include_router(ocr_router)
v1_routers.include_router(timeline_router)
v1_routers.include_router(guide_router)
v1_routers.include_router(message_router)
v1_routers.include_router(message_template_router)
v1_routers.include_router(lab_baseline_router)
v1_routers.include_router(guide_copy_router)
v1_routers.include_router(patient_link_management_router)
v1_routers.include_router(patient_guide_router)
v1_routers.include_router(patient_checkin_router)
v1_routers.include_router(patient_otp_router)
v1_routers.include_router(chatbot_router)
