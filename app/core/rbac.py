"""역할 기반 접근 제어의 단일 권한표 — KEY-21.

역할을 하나라도 가지고 있으면 해당 역할이 여는 권한을 얻는 OR 규칙이다.
알 수 없는 역할이나 권한은 예외 대신 기본 차단한다.
"""

from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    STAFF = "staff"
    DOCTOR = "doctor"
    ADMIN = "admin"


class Permission(StrEnum):
    PATIENT_READ = "patient:read"
    PATIENT_WRITE = "patient:write"
    OCR_UPLOAD = "ocr:upload"
    GUIDE_DRAFT = "guide:draft"
    SMS_SEND = "sms:send"
    GUIDE_APPROVE = "guide:approve"
    GUIDE_RETURN = "guide:return"
    LAB_TARGET_SET = "lab_target:set"
    PRESCRIPTION_SET_WRITE = "prescription_set:write"
    STAFF_MANAGE = "staff:manage"
    CLINIC_MANAGE = "clinic:manage"
    SMS_TEMPLATE_MANAGE = "sms_template:manage"
    AUDIT_READ = "audit:read"


PERMISSION_ROLES: dict[Permission, frozenset[Role]] = {
    Permission.PATIENT_READ: frozenset({Role.STAFF, Role.DOCTOR}),
    Permission.PATIENT_WRITE: frozenset({Role.STAFF, Role.DOCTOR}),
    Permission.OCR_UPLOAD: frozenset({Role.STAFF, Role.DOCTOR}),
    Permission.GUIDE_DRAFT: frozenset({Role.STAFF, Role.DOCTOR}),
    Permission.SMS_SEND: frozenset({Role.STAFF, Role.DOCTOR}),
    Permission.GUIDE_APPROVE: frozenset({Role.DOCTOR}),
    Permission.GUIDE_RETURN: frozenset({Role.DOCTOR}),
    Permission.LAB_TARGET_SET: frozenset({Role.DOCTOR}),
    Permission.PRESCRIPTION_SET_WRITE: frozenset({Role.DOCTOR}),
    Permission.STAFF_MANAGE: frozenset({Role.ADMIN}),
    Permission.CLINIC_MANAGE: frozenset({Role.ADMIN}),
    Permission.SMS_TEMPLATE_MANAGE: frozenset({Role.ADMIN}),
    Permission.AUDIT_READ: frozenset({Role.ADMIN}),
}


def has_permission(roles: Iterable[str], permission: Permission | str) -> bool:
    """Return whether any known role grants ``permission``.

    Values are matched exactly. Case-folding or whitespace trimming could turn a
    malformed stored role into authority, so malformed values remain powerless.
    """
    try:
        required_roles = PERMISSION_ROLES[Permission(permission)]
    except (ValueError, KeyError):
        return False

    known_roles: set[Role] = set()
    for role in roles:
        try:
            known_roles.add(Role(role))
        except (TypeError, ValueError):
            continue
    return bool(known_roles.intersection(required_roles))
