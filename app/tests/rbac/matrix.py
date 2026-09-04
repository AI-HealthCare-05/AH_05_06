"""역할·권한 매트릭스 — 무엇이 허용되고 무엇이 막혀야 하는가.

KEY-23. 이 파일은 **테스트가 소유하는 계약**이다.
KEY-21이 `app/core/rbac.py`에 구현하면 아래 표가 그대로 검증 기준이 된다.

용어 (KEY-9 결정 · 2026-08-19)
----------------------------
staff · doctor 는 **역할**이다 — 무엇을 하는 사람인가.
admin 은 **권한**이다 — 의원 운영을 관리할 수 있는가.

둘은 직교한다. admin 을 켠다고 진료 화면이 열리지 않고,
admin 을 끈다고 진료 권한이 사라지지 않는다.

저장은 `staff.roles` jsonb 배열 하나로 한다. 개념이 다르다고 컬럼을
나누면 검사가 두 곳으로 흩어진다. 배열이면 검사가 한 줄이다.

    "doctor" in roles  ->  안내문 승인
"""

from enum import StrEnum


class Role(StrEnum):
    STAFF = "staff"
    DOCTOR = "doctor"
    ADMIN = "admin"


class Permission(StrEnum):
    """화면에서 뽑은 권한. 오른쪽 주석은 그 권한이 쓰이는 프레임이다."""

    # 진료 — 스탭과 의사가 함께 쓴다
    PATIENT_READ = "patient:read"  # S1-1 S1-4 S2-1 S2-2
    PATIENT_WRITE = "patient:write"  # S1-2 S1-3
    OCR_UPLOAD = "ocr:upload"  # S1-5 ~ S1-9
    GUIDE_DRAFT = "guide:draft"  # S1-11 S1-12
    SMS_SEND = "sms:send"  # S1-13 S1-14

    # 의료 판단 — 의사만
    GUIDE_APPROVE = "guide:approve"  # D1-3 D2-1
    GUIDE_RETURN = "guide:return"  # D1-4
    LAB_TARGET_SET = "lab_target:set"  # D2-2
    PRESCRIPTION_SET_WRITE = "prescription_set:write"  # D2-3 (+ 본인 소유)

    # 의원 운영 — 관리자만
    STAFF_MANAGE = "staff:manage"  # A1-1 A1-2 A1-3
    CLINIC_MANAGE = "clinic:manage"  # A1-4
    SMS_TEMPLATE_MANAGE = "sms_template:manage"  # A1-5
    AUDIT_READ = "audit:read"  # A1-6 A1-7


#: 권한 -> 그 권한을 여는 역할들. 하나라도 가지고 있으면 통과한다(OR).
MATRIX: dict[Permission, frozenset[Role]] = {
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

#: 의료 판단에 속하는 권한. admin 을 아무리 얹어도 열리지 않아야 한다.
MEDICAL_JUDGEMENT = frozenset(
    {
        Permission.GUIDE_APPROVE,
        Permission.GUIDE_RETURN,
        Permission.LAB_TARGET_SET,
        Permission.PRESCRIPTION_SET_WRITE,
    }
)

#: 의원 운영에 속하는 권한. 진료 역할만으로는 열리지 않아야 한다.
CLINIC_OPERATION = frozenset(
    {
        Permission.STAFF_MANAGE,
        Permission.CLINIC_MANAGE,
        Permission.SMS_TEMPLATE_MANAGE,
        Permission.AUDIT_READ,
    }
)

#: 역할만으로는 부족하고 **소유자 검사가 더 필요한** 권한.
#: D2-3 — 의사는 자기가 만든 처방 세트만 고칠 수 있다.
#: 역할 검사를 통과했다고 끝이 아니라는 뜻이다.
OWNERSHIP_REQUIRED = frozenset({Permission.PRESCRIPTION_SET_WRITE})

#: 실제로 존재할 수 있는 역할 조합 — **다섯**.
#:
#: 예전에는 일곱이었다. A1-2 가 중복 선택을 허용하므로 `2^3 - 1 = 7` 이라고
#: 멱집합을 채운 것인데, 조합마다 필요가 있어서 고른 것이 아니었다.
#:
#: **`staff` ⊂ `doctor` 다.** `MATRIX` 에서 staff 가 가진 권한
#: (`patient:read/write` · `ocr:upload` · `guide:draft` · `sms:send`)을 doctor 가
#: 그대로 가진다. 그래서 `staff|doctor` 는 `doctor` 하나와 **권한이 완전히
#: 같고**, 조합으로 둘 이유가 없다. `staff|doctor|admin` 도 마찬가지다
#: (2026-09-04 이희진 결정, KEY-269).
#:
#: 남은 멀티롤 둘은 **admin 오버레이**다 — 각각 날카로운 물음이 있다.
#:   `staff+admin`  스탭 일은 되고 의료 승인만 막히는가 (KEY-9)
#:   `doctor+admin` admin 이 의사의 승인을 방해하지 않는가
#:
#: 빈 조합은 「역할과 권한을 합쳐 하나 이상」 규칙에 걸려 저장될 수 없다.
VALID_COMBINATIONS: tuple[frozenset[Role], ...] = (
    frozenset({Role.STAFF}),
    frozenset({Role.DOCTOR}),
    frozenset({Role.ADMIN}),
    frozenset({Role.STAFF, Role.ADMIN}),
    frozenset({Role.DOCTOR, Role.ADMIN}),
)


def expected(roles: frozenset[Role] | set[Role], permission: Permission) -> bool:
    """이 조합이 이 권한을 가져야 하는가 — 매트릭스가 말하는 정답.

    OR 규칙이다. 역할 하나라도 그 권한을 열면 통과한다.
    """
    return bool(MATRIX[permission] & set(roles))


def label(roles: frozenset[Role] | set[Role]) -> str:
    """실패 메시지에 쓸 이름. 정렬해서 순서가 흔들리지 않게 한다."""
    return "+".join(sorted(r.value for r in roles)) or "(없음)"
