"""매트릭스 자체가 말이 되는가 — 구현도 DB도 필요 없다.

KEY-23. 이 검사들은 지금 당장 돈다.
권한표를 잘못 고치는 순간 여기서 걸린다.

가드 구현(KEY-21)을 검증하는 것은 `test_rbac_guard.py` 쪽이다.
"""

import pytest

from app.tests.rbac.matrix import (
    CLINIC_OPERATION,
    MATRIX,
    MEDICAL_JUDGEMENT,
    OWNERSHIP_REQUIRED,
    VALID_COMBINATIONS,
    Permission,
    Role,
    expected,
    label,
)


class TestMatrixShape:
    def test_every_permission_is_in_the_table(self) -> None:
        missing = set(Permission) - set(MATRIX)
        assert not missing, f"권한표에 빠진 권한: {sorted(p.value for p in missing)}"

    def test_no_permission_is_unreachable(self) -> None:
        """역할이 비어 있는 줄은 그 기능을 영영 못 쓴다는 뜻이다. 실수일 확률이 높다."""
        orphans = [p.value for p, roles in MATRIX.items() if not roles]
        assert not orphans, f"어떤 역할로도 열리지 않는 권한: {orphans}"

    def test_the_combinations_are_the_five_we_chose(self) -> None:
        """조합은 **다섯**이다 — 멱집합을 채운 일곱이 아니다 (KEY-269).

        `staff` ⊂ `doctor` 라 `staff|doctor` 는 `doctor` 하나와 권한이 완전히
        같다. 남은 멀티롤 둘은 admin 오버레이이고 각각 물음이 있다.

        빈 조합은 「역할과 권한을 합쳐 하나 이상」 규칙에 걸려 저장될 수 없다.
        """
        assert len(VALID_COMBINATIONS) == 5
        assert len(set(VALID_COMBINATIONS)) == 5, "중복된 조합이 있다"
        assert frozenset() not in VALID_COMBINATIONS

    def test_staff_and_doctor_never_sit_in_the_same_account(self) -> None:
        """**둘을 한 계정에 같이 주지 않는다** — 개수만 세면 무엇이 빠졌는지 모른다.

        `staff` 권한이 `doctor` 권한에 통째로 들어 있으므로, 둘을 함께 주는 것은
        `doctor` 하나와 같은 말이면서 「겸직」이라는 없는 뜻을 만든다.
        """
        both = [combo for combo in VALID_COMBINATIONS if {Role.STAFF, Role.DOCTOR} <= combo]
        assert not both, f"staff 와 doctor 가 함께 있는 조합: {[sorted(r.value for r in c) for c in both]}"

    def test_staff_permissions_are_a_subset_of_doctor(self) -> None:
        """조합을 줄인 **근거 자체**를 잰다.

        `staff` ⊂ `doctor` 가 깨지면 `staff|doctor` 를 뺀 것이 틀린 결정이 된다 —
        그때는 조합을 되살려야 하고, 이 검사가 그것을 알려 준다.
        """
        staff_can = {p for p, roles in MATRIX.items() if Role.STAFF in roles}
        doctor_can = {p for p, roles in MATRIX.items() if Role.DOCTOR in roles}

        missing = sorted(p.value for p in staff_can - doctor_can)
        assert not missing, f"의사가 못 하는 스탭 권한이 생겼다: {missing} — staff|doctor 조합을 되살려야 한다"

    def test_permission_groups_do_not_overlap(self) -> None:
        assert not (MEDICAL_JUDGEMENT & CLINIC_OPERATION)


class TestAdminIsNotAMedicalRole:
    """KEY-9 결정의 핵심 — 관리자는 역할이 아니라 권한이다.

    어드민을 켠다고 진료 권한이 생기지 않고, 꺼도 사라지지 않는다.
    """

    @pytest.mark.parametrize("permission", sorted(MEDICAL_JUDGEMENT), ids=lambda p: p.value)
    def test_admin_alone_opens_no_medical_judgement(self, permission: Permission) -> None:
        assert not expected({Role.ADMIN}, permission), (
            f"{permission.value}가 admin 단독으로 열린다 — 관리자는 의료 역할이 아니다"
        )

    def test_admin_alone_opens_nothing_outside_clinic_operation(self) -> None:
        opened = [p.value for p in Permission if expected({Role.ADMIN}, p) and p not in CLINIC_OPERATION]
        assert not opened, f"admin 단독인데 의원 운영 밖의 권한이 열린다: {opened}"

    @pytest.mark.parametrize("permission", sorted(CLINIC_OPERATION), ids=lambda p: p.value)
    def test_clinic_operation_needs_admin(self, permission: Permission) -> None:
        """원장님이라고 직원 계정을 만들 수 있는 것이 아니다."""
        assert not expected({Role.STAFF, Role.DOCTOR}, permission), (
            f"{permission.value}가 진료 역할만으로 열린다 — 의원 운영은 admin 권한이다"
        )


class TestAcceptanceCriteria:
    """티켓이 글로 적어 둔 인수조건을 실행 가능한 형태로 옮긴 것."""

    def test_admin_plus_staff_cannot_approve(self) -> None:
        """KEY-9 인수조건 — 「관리자+스탭 사용자가 의료 승인을 수행할 수 없음」.

        이 한 줄이 무너지면 의사가 안 본 안내문이 환자에게 나간다.
        """
        assert not expected({Role.ADMIN, Role.STAFF}, Permission.GUIDE_APPROVE)

    def test_admin_plus_staff_keeps_staff_work(self) -> None:
        """막는 것만 맞으면 안 된다. 열려야 할 것도 열려야 한다."""
        for permission in (
            Permission.PATIENT_READ,
            Permission.PATIENT_WRITE,
            Permission.OCR_UPLOAD,
            Permission.GUIDE_DRAFT,
            Permission.SMS_SEND,
        ):
            assert expected({Role.ADMIN, Role.STAFF}, permission), (
                f"admin+staff가 {permission.value}를 못 한다 — 스탭 기능은 살아 있어야 한다"
            )

    def test_admin_plus_doctor_can_approve(self) -> None:
        """의사 역할이 있으니 열린다. admin이 방해하지 않는다."""
        assert expected({Role.ADMIN, Role.DOCTOR}, Permission.GUIDE_APPROVE)

    def test_staff_drafts_but_does_not_approve(self) -> None:
        """S1-11에서 만들고 D1-3에서 의사가 승인한다 — 그 경계다."""
        assert expected({Role.STAFF}, Permission.GUIDE_DRAFT)
        assert not expected({Role.STAFF}, Permission.GUIDE_APPROVE)

    @pytest.mark.parametrize("roles", VALID_COMBINATIONS, ids=label)
    def test_approval_needs_doctor_in_every_combination(self, roles: frozenset[Role]) -> None:
        """조합을 하나씩 세는 대신 전수로 확인한다. 역할이 늘어도 이 검사는 그대로 산다."""
        assert expected(roles, Permission.GUIDE_APPROVE) is (Role.DOCTOR in roles)


class TestOwnership:
    def test_ownership_checks_belong_to_medical_judgement(self) -> None:
        assert OWNERSHIP_REQUIRED <= MEDICAL_JUDGEMENT

    def test_prescription_set_needs_more_than_a_role(self) -> None:
        """D2-3 — 의사라고 남의 처방 세트를 고칠 수는 없다.

        역할 검사를 통과해도 소유자 검사가 남는다. 두 검사는 별개다.
        """
        assert Permission.PRESCRIPTION_SET_WRITE in OWNERSHIP_REQUIRED
        assert expected({Role.DOCTOR}, Permission.PRESCRIPTION_SET_WRITE), (
            "역할 검사는 통과해야 한다 — 막히는 것은 그다음 소유자 검사다"
        )
