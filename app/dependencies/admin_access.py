"""어드민 화면이 지나는 문 — KEY-321.

`patient_access.py` 와 같은 모양이다: 인증된 `Staff` 를 요청이 못 건드리는
불변 값으로 옮기고, 권한을 여기서 본다. 라우터마다 `has_permission` 을 다시
적으면 한 곳을 빠뜨렸을 때 그 경로만 조용히 열린다.

**병원을 요청에서 받지 않는다.** 어드민 API 는 「내 의원의 직원」을 다루는데,
그 「내 의원」이 요청 본문이나 질의 문자열에서 오면 값 하나 바꿔 남의 의원
직원을 만들거나 볼 수 있다. 토큰이 가리키는 계정에서만 가져온다.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.core.api_errors import ApiError
from app.core.rbac import Permission, has_permission
from app.dependencies.staff_auth import get_current_staff
from app.models.staffs import Staff


@dataclass(frozen=True, slots=True)
class AdminActor:
    staff_id: int
    hospital_id: int
    roles: frozenset[str]


async def get_admin_actor(staff: Annotated[Staff, Depends(get_current_staff)]) -> AdminActor:
    return AdminActor(
        staff_id=staff.staff_id,
        hospital_id=staff.hospital_id,
        roles=frozenset(staff.roles or []),
    )


async def require_audit_read(
    actor: Annotated[AdminActor, Depends(get_admin_actor)],
) -> AdminActor:
    """감사 기록을 읽을 수 있는가 — `admin` 만이다 (KEY-322).

    `STAFF_MANAGE` 와 여는 역할이 같지만 뜻이 다르다. 나중에 「감사만 보는
    역할」이 생기면 여기만 바뀌고 직원 관리는 그대로다 — 한 권한으로 둘을
    겸하면 그날 둘을 갈라내야 한다. 권한표가 이미 `AUDIT_READ` 를 갖고 있다.
    """
    if not has_permission(actor.roles, Permission.AUDIT_READ):
        raise ApiError(403, "FORBIDDEN", "감사 기록을 볼 권한이 없습니다.")
    return actor


async def require_staff_manage(
    actor: Annotated[AdminActor, Depends(get_admin_actor)],
) -> AdminActor:
    """직원 계정을 보고 만들 수 있는가 — `admin` 만이다 (`PERMISSION_ROLES`).

    **403 이지 404 가 아니다.** 이 경로가 있다는 사실 자체는 비밀이 아니고,
    없는 척하면 관리자가 「내 권한이 없구나」 대신 「기능이 없구나」로 읽는다.
    """
    if not has_permission(actor.roles, Permission.STAFF_MANAGE):
        raise ApiError(403, "FORBIDDEN", "직원 계정을 관리할 권한이 없습니다.")
    return actor
