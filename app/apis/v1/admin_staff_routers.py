"""어드민 — 직원 목록·추가 (A1-1 · A1-2). KEY-321.

`docs/api/hospital.md` 2절이 미뤄 둔 자리다: 「형식 검사는 계정을 만들 때
한다」, 「`signup` 정리는 계정 관리(A1-2) 몫」.

**경로 앞에 `/admin` 을 붙인다.** `/staffs` 로 두면 「직원이 쓰는 API」처럼
읽히는데, 이 둘은 **직원을 관리하는** API 라 관리자만 지난다. 경로 이름이
권한을 말해 주면 다음 사람이 여기에 스탭용 조회를 얹지 않는다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.api_errors import ContractRoute
from app.dependencies.admin_access import AdminActor, require_staff_manage
from app.dtos.admin_staffs import StaffCreatedResponse, StaffCreateRequest, StaffListResponse
from app.services.admin_staffs import AdminStaffService

admin_staff_router = APIRouter(prefix="/admin/staffs", tags=["admin"], route_class=ContractRoute)


@admin_staff_router.get("", response_model=StaffListResponse)
async def list_staffs(
    actor: Annotated[AdminActor, Depends(require_staff_manage)],
) -> StaffListResponse:
    """A1-1 — 내 의원 직원 목록. 이름 · 아이디 · 역할 · 상태."""
    return await AdminStaffService.list_staffs(actor)


@admin_staff_router.post("", response_model=StaffCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    request: StaffCreateRequest,
    actor: Annotated[AdminActor, Depends(require_staff_manage)],
) -> StaffCreatedResponse:
    """A1-2 — 직원 추가. 만든 계정은 첫 로그인에서 비밀번호를 바꿔야 한다(L-3)."""
    return await AdminStaffService.create_staff(actor, request)
