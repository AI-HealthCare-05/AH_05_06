"""서버 가드가 매트릭스대로 판정하는가 — KEY-21 구현이 들어오면 켜진다.

KEY-23. `app/core/rbac.py`가 아직 없으므로 지금은 통째로 skip 된다.
구현이 들어오는 순간 이 파일이 저절로 돌기 시작한다.

KEY-21이 만들어야 하는 것
------------------------
    # app/core/rbac.py
    class Role(StrEnum):        STAFF="staff" / DOCTOR="doctor" / ADMIN="admin"
    class Permission(StrEnum):  값은 app/tests/rbac/matrix.py 와 같아야 한다
    def has_permission(roles: Iterable[str], permission: Permission | str) -> bool

`has_permission`은 **순수 함수**여야 한다 — DB도 요청 객체도 건드리지 않는다.
그래야 65가지 조합을 DB 없이 돌릴 수 있고, 판정 규칙이 한 곳에 모인다.
FastAPI 의존성은 이 함수를 감싸기만 한다.

엔드포인트에서 실제로 403이 나오는지는 엔드포인트가 생긴 뒤에 붙인다.
"""

import pytest

from app.tests.rbac.matrix import VALID_COMBINATIONS, Permission, Role, expected, label

rbac = pytest.importorskip(
    "app.core.rbac",
    reason="KEY-21 서버 가드 미구현 — app/core/rbac.py 가 들어오면 이 파일이 켜진다",
)


def call(roles: frozenset[Role] | set[Role] | list[str], permission: Permission) -> bool:
    return bool(rbac.has_permission([str(r) for r in roles], permission.value))


class TestContract:
    """구현이 테스트와 같은 낱말을 쓰는가. 여기가 어긋나면 아래는 볼 필요도 없다."""

    def test_role_names_match(self) -> None:
        assert {r.value for r in rbac.Role} == {r.value for r in Role}

    def test_permission_names_match(self) -> None:
        implemented = {p.value for p in rbac.Permission}
        contracted = {p.value for p in Permission}
        assert implemented >= contracted, f"구현에 없는 권한: {sorted(contracted - implemented)}"
        assert not (implemented - contracted), f"계약에 없는 권한이 구현에만 있다: {sorted(implemented - contracted)}"


@pytest.mark.parametrize("permission", sorted(Permission), ids=lambda p: p.value)
@pytest.mark.parametrize("roles", VALID_COMBINATIONS, ids=label)
class TestEveryCombination:
    """5개 조합 × 13개 권한 = 65가지를 전수로 확인한다.

    표를 눈으로 읽는 대신 전부 돌린다. 권한이 늘어도 검사가 저절로 따라 늘어난다.
    """

    def test_matches_the_matrix(self, roles: frozenset[Role], permission: Permission) -> None:
        want = expected(roles, permission)
        assert call(roles, permission) is want, (
            f"{label(roles)} 이 {permission.value} 를 {'가져야 하는데 막혔다' if want else '가지면 안 되는데 통과했다'}"
        )


class TestDenyByDefault:
    """모르면 막는다. 권한 검사가 흔들리는 곳은 대개 여기다."""

    @pytest.mark.parametrize("permission", sorted(Permission), ids=lambda p: p.value)
    def test_no_roles_opens_nothing(self, permission: Permission) -> None:
        assert call([], permission) is False

    @pytest.mark.parametrize(
        "unknown",
        ["owner", "superadmin", "root", "master", "", "  ", "admin;doctor"],
        ids=["owner", "superadmin", "root", "master", "empty", "blank", "injected"],
    )
    def test_unknown_roles_carry_no_power(self, unknown: str) -> None:
        """폐기한 「최상위관리자」 같은 옛 이름이 남아 있어도 권한이 생기면 안 된다."""
        for permission in Permission:
            assert call([unknown], permission) is False, f"{unknown!r} 이 {permission.value} 를 열었다"

    @pytest.mark.parametrize("variant", ["Doctor", "DOCTOR", " doctor", "doctor ", "dokter"], ids=repr)
    def test_misspellings_do_not_pass(self, variant: str) -> None:
        """대소문자나 공백을 너그럽게 받아 주면 오타가 권한이 된다."""
        assert call([variant], Permission.GUIDE_APPROVE) is False

    def test_unknown_mixed_in_leaves_the_rest_intact(self) -> None:
        """알 수 없는 값이 섞였다고 통째로 거부하지도, 통째로 허용하지도 않는다."""
        assert call(["staff", "superadmin"], Permission.PATIENT_READ) is True
        assert call(["staff", "superadmin"], Permission.GUIDE_APPROVE) is False

    def test_unknown_permission_is_denied(self) -> None:
        assert rbac.has_permission(["staff", "doctor", "admin"], "guide:delete_everything") is False


class TestPurity:
    def test_same_input_same_answer(self) -> None:
        for _ in range(3):
            assert call({Role.ADMIN, Role.STAFF}, Permission.GUIDE_APPROVE) is False

    def test_does_not_mutate_the_given_list(self) -> None:
        roles = ["staff", "admin"]
        rbac.has_permission(roles, Permission.GUIDE_APPROVE.value)
        assert roles == ["staff", "admin"]

    def test_order_does_not_change_the_result(self) -> None:
        assert call(["admin", "staff"], Permission.PATIENT_READ) == call(["staff", "admin"], Permission.PATIENT_READ)
