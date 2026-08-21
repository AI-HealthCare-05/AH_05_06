from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, status

from app.core.rbac import Permission, has_permission
from app.dependencies.staff_auth import get_current_staff
from app.models.staffs import Staff
from app.ocr.errors import OcrApiError


@dataclass(frozen=True)
class OcrActor:
    staff_id: int
    hospital_id: int
    roles: frozenset[str]


def _role_value(role: object) -> str:
    value = getattr(role, "value", role)
    return str(value)


async def get_ocr_actor(staff: Annotated[Staff, Depends(get_current_staff)]) -> OcrActor:
    """OCR 을 부를 수 있는 사람인지 보고, 그 사람의 병원을 함께 준다.

    예전에는 `get_request_user` 에 걸려 있었다. 그것은 토큰에서 `user_id` 를
    찾는데, **제품 안에 그 클레임을 담은 토큰을 만드는 경로가 없다** — 직원
    토큰은 `staff_id` 를 담는다. 그래서 OCR API 다섯이 전부 401 이었다.
    설령 그 토큰이 있었어도 `User` 에는 `hospital_id` 도 `roles` 도 없어
    403 이 됐을 것이다 (KEY-116).

    속성을 `getattr` 로 감싸지 않는다 — 배선이 틀리면 조용히 403 이 되는 대신
    소리 내어 터지는 편이 낫다. 그 침묵이 이 버그를 숨긴 자리였다.

    **판정은 `has_permission` 에 맡긴다.** 여기에 역할 집합을 따로 두면 권한표와
    어긋날 자리가 하나 더 생긴다 — `app/core/rbac.py` 가 정본이고, 그 값은
    `app/tests/rbac/matrix.py` 가 지킨다. `admin` 은 역할이 아니라 권한이라
    혼자서는 진료 화면을 열지 못한다(KEY-9).
    """
    roles = frozenset(_role_value(role) for role in (staff.roles or ()))
    if not has_permission(roles, Permission.OCR_UPLOAD):
        raise OcrApiError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "OCR 접근 권한이 없습니다.")
    return OcrActor(staff_id=staff.staff_id, hospital_id=staff.hospital_id, roles=roles)
