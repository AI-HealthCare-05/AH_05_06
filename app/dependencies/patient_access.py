from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.core.api_errors import ApiError
from app.core.rbac import Permission, has_permission
from app.dependencies.staff_auth import get_current_staff
from app.models.staffs import Staff


@dataclass(frozen=True)
class ClinicalActor:
    staff_id: int
    hospital_id: int | None
    roles: frozenset[str]


async def get_clinical_actor(staff: Annotated[Staff, Depends(get_current_staff)]) -> ClinicalActor:
    """Adapt the authenticated Staff without trusting request-supplied scope."""
    return ClinicalActor(
        staff_id=staff.staff_id,
        hospital_id=getattr(staff, "hospital_id", None),
        roles=frozenset(staff.roles or []),
    )


def _require_patient_permission(actor: ClinicalActor, permission: Permission) -> ClinicalActor:
    if actor.hospital_id is None or not has_permission(actor.roles, permission):
        raise ApiError(403, "FORBIDDEN", "환자·진료 정보에 접근할 권한이 없습니다.")
    return actor


async def require_patient_read(
    actor: Annotated[ClinicalActor, Depends(get_clinical_actor)],
) -> ClinicalActor:
    return _require_patient_permission(actor, Permission.PATIENT_READ)


async def require_patient_write(
    actor: Annotated[ClinicalActor, Depends(get_clinical_actor)],
) -> ClinicalActor:
    return _require_patient_permission(actor, Permission.PATIENT_WRITE)


async def require_sms_send(
    actor: Annotated[ClinicalActor, Depends(get_clinical_actor)],
) -> ClinicalActor:
    return _require_patient_permission(actor, Permission.SMS_SEND)


# 이전 이름을 쓰는 코드가 권한 검사를 우회하지 않도록 읽기 가드로 유지한다.
require_patient_access = require_patient_read
