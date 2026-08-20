from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, status

from app.core.rbac import Permission, has_permission
from app.dependencies.security import get_request_user
from app.models.users import User
from app.ocr.errors import OcrApiError


@dataclass(frozen=True)
class OcrActor:
    user_id: int
    hospital_id: int
    roles: frozenset[str]


def _role_value(role: object) -> str:
    value = getattr(role, "value", role)
    return str(value)


async def get_ocr_actor(user: Annotated[User, Depends(get_request_user)]) -> OcrActor:
    hospital_id = getattr(user, "hospital_id", None)
    roles = frozenset(_role_value(role) for role in (getattr(user, "roles", None) or ()))
    user_id = getattr(user, "staff_id", getattr(user, "id", None))
    if (
        not isinstance(user_id, int)
        or not isinstance(hospital_id, int)
        or not has_permission(roles, Permission.OCR_UPLOAD)
    ):
        raise OcrApiError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "OCR 접근 권한이 없습니다.")
    return OcrActor(user_id=user_id, hospital_id=hospital_id, roles=roles)
