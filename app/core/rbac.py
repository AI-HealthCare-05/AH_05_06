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


#: 계정 하나가 가질 수 있는 역할 조합 — **다섯**. 멱집합(일곱)이 아니다.
#:
#: `staff` ⊂ `doctor` 라 `staff|doctor` 는 `doctor` 하나와 권한이 **완전히 같다**.
#: 겸직이라는 없는 뜻만 만들어서 뺐다 (2026-09-04 이희진 결정, KEY-269).
#: 남은 멀티롤 둘은 admin 오버레이다 — `staff+admin` · `doctor+admin`.
#:
#: **왜 다섯인지의 근거는 `app/tests/rbac/matrix.py` 가 갖는다.** 그 파일은
#: 검사가 독립적으로 소유한 계약이라 여기서 읽어 오지 않는다 — 구현이 제
#: 답안을 채점하게 된다. 두 표가 어긋나면 `test_rbac_guard.py` 가 잡는다.
#:
#: 여기 이것이 **운영 쪽 한 벌**이다. 예전에는 표가 검사에만 있어서, A1-2 가
#: 계정을 만들 때 막을 근거가 운영 코드에 없었다 — 어떤 조합이든 저장됐다.
#: `Staff.save()` 는 「모르는 역할」만 보고 조합은 안 본다 (KEY-321).
VALID_ROLE_COMBINATIONS: tuple[frozenset[Role], ...] = (
    frozenset({Role.STAFF}),
    frozenset({Role.DOCTOR}),
    frozenset({Role.ADMIN}),
    frozenset({Role.STAFF, Role.ADMIN}),
    frozenset({Role.DOCTOR, Role.ADMIN}),
)


def is_valid_role_combination(roles: Iterable[str]) -> bool:
    """이 조합으로 계정을 만들 수 있는가.

    **모르는 값이 하나라도 있으면 거짓이다.** `has_permission` 은 모르는 역할을
    조용히 버리고 남은 것으로 판정하는데 — 이미 있는 계정을 읽는 자리라 그것이
    맞다 — 여기는 **새로 만드는 자리**다. 버리고 통과시키면 `["admin","typo"]`
    가 `["admin"]` 으로 저장돼 등록자가 고른 것과 저장된 것이 갈린다.

    같은 역할을 두 번 고른 것도 막는다. 집합으로 접으면 통과하지만, 화면이
    보낸 목록과 저장될 목록이 달라진다.
    """
    values = list(roles)
    try:
        known = frozenset(Role(role) for role in values)
    except (TypeError, ValueError):
        return False
    if len(known) != len(values):
        return False
    return known in VALID_ROLE_COMBINATIONS


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
