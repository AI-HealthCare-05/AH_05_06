"""어드민 — 의원 정보 (A1-4). KEY-331.

`admin_staff_routers.py` 와 같은 규율이다: 경로 앞에 `/admin` 을 붙이고
권한으로 잠근다. 다만 **이 화면 몫의 권한은 `CLINIC_MANAGE`** 다 — 직원 관리와
여는 역할이 같아도 뜻이 다르고, 권한표가 이미 둘을 갈라 두었다.

**`/admin/hospital` 이지 `/admin/hospitals` 가 아니다.** 지금 판에 의원은
하나다. 복수형으로 두면 다음 사람이 목록·생성·삭제를 얹을 자리가 있다고 읽는데,
그런 것은 아직 이 제품에 없다. 「의원 하나」는 잠정적인 범위 축소이지 배포
구조가 아니다(#290 에서 「폐쇄망」 주장을 철회했다).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.api_errors import ContractRoute
from app.dependencies.admin_access import AdminActor, require_clinic_manage
from app.dtos.admin_hospital import HospitalResponse, HospitalUpdateRequest
from app.services.admin_hospital import AdminHospitalService

admin_hospital_router = APIRouter(prefix="/admin/hospital", tags=["admin"], route_class=ContractRoute)


@admin_hospital_router.get("", response_model=HospitalResponse)
async def get_hospital(
    actor: Annotated[AdminActor, Depends(require_clinic_manage)],
) -> HospitalResponse:
    """A1-4 — 내 의원 정보."""
    return await AdminHospitalService.get_hospital(actor)


@admin_hospital_router.patch("", response_model=HospitalResponse)
async def update_hospital(
    request: HospitalUpdateRequest,
    actor: Annotated[AdminActor, Depends(require_clinic_manage)],
) -> HospitalResponse:
    """A1-4 — 의원 정보 수정.

    `booking_url` 이 바뀌면 **다음 소진·재진 문자부터** 그 주소가 나간다. 이미
    보낸 문자는 바뀌지 않는다(`sent_body` 는 보낸 그대로 남는다).
    """
    return await AdminHospitalService.update_hospital(actor, request)
