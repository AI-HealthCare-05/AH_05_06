from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.core.api_errors import ApiError
from app.dependencies.security import get_request_user
from app.models.users import User


@dataclass(frozen=True)
class ClinicalActor:
    user_id: int
    hospital_id: int | None
    roles: frozenset[str]


async def get_clinical_actor(user: Annotated[User, Depends(get_request_user)]) -> ClinicalActor:
    """Adapt the authenticated staff contract without trusting request-supplied scope."""
    return ClinicalActor(
        user_id=user.id,
        hospital_id=getattr(user, "hospital_id", None),
        roles=frozenset(getattr(user, "roles", [])),
    )


async def require_patient_access(
    actor: Annotated[ClinicalActor, Depends(get_clinical_actor)],
) -> ClinicalActor:
    if actor.hospital_id is None or not actor.roles.intersection({"staff", "doctor"}):
        raise ApiError(403, "FORBIDDEN", "환자·진료 정보에 접근할 권한이 없습니다.")
    return actor
