from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse as Response

from app.dtos.auth import SignUpRequest
from app.services.auth import AuthService

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 로그인·갱신·로그아웃은 `staff_auth_routers.py` 가 갖는다 — 계약(KEY-8)은 email 이
# 아니라 login_id 로 받고, 잠금·강제 변경·세션 확인이 함께 붙는다.
#
# 레거시 `GET /auth/token/refresh` 는 **지웠다.** 서명·만료만 보고 새 액세스
# 토큰을 찍어 주는 경로였는데, 리프레시 쿠키가 `/api/v1/auth` 에 실려 이쪽에도
# 그대로 붙었다. 그래서 로그아웃했거나 rotation 으로 폐기됐거나 퇴사한 직원의
# 토큰이어도 만료 전까지 계속 새 액세스 토큰을 받을 수 있었다 —
# 이 티켓이 만든 로그아웃 · 재사용 감지 · 유휴 만료 · 퇴사자 차단이 전부
# 이 한 경로로 우회됐다. 같은 일은 `POST /auth/refresh` 가 세션까지 보고 한다.
#
# `signup` 정리는 계정 관리(A1-2) 몫이라 남긴다.


@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignUpRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    await auth_service.signup(request)
    return Response(content={"detail": "회원가입이 성공적으로 완료되었습니다."}, status_code=status.HTTP_201_CREATED)
