from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.core.api_errors import ApiError
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


async def require_patient_access(
    actor: Annotated[ClinicalActor, Depends(get_clinical_actor)],
) -> ClinicalActor:
    if actor.hospital_id is None or not actor.roles.intersection({"staff", "doctor"}):
        raise ApiError(403, "FORBIDDEN", "환자·진료 정보에 접근할 권한이 없습니다.")
    return actor
