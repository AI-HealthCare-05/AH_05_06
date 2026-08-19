"""합성 직원 계정이 앞뒤가 맞는가 — DB도 서버도 필요 없다.

KEY-10. CSV를 고치다 어긋나면 여기서 걸린다.
`KEY-24` 통합 테스트가 이 계정들을 믿고 쓰므로, 픽스처가 먼저 성해야 한다.
"""

import re

import pytest

from app.tests.fixtures.staff import ROLE_SEPARATOR, STAFF, Staff, by_id, by_login, with_roles

KNOWN_ROLES = {"staff", "doctor", "admin"}
LOGIN_ID_PATTERN = re.compile(r"^[a-z0-9]{4,}$")  # spec-medical.md staff 표

#: 역할 조합 2^3 - 1. app/tests/rbac/matrix.py 의 VALID_COMBINATIONS 와 같아야 한다.
ALL_COMBINATIONS = frozenset(
    frozenset(c)
    for c in (
        {"staff"},
        {"doctor"},
        {"admin"},
        {"staff", "doctor"},
        {"staff", "admin"},
        {"doctor", "admin"},
        {"staff", "doctor", "admin"},
    )
)


class TestFileIsSane:
    def test_the_csv_is_not_empty(self) -> None:
        assert STAFF, "직원 CSV가 비어 있다"

    def test_no_password_column(self) -> None:
        """AGENTS.md — 비밀번호를 커밋에 남기지 않는다.

        시드가 SEED_STAFF_PASSWORD 에서 받는다. 저장소에는 없다.
        """
        fields = {f for f in Staff.__dataclass_fields__ if f != "must_change_password"}
        leaked = [f for f in fields if "password" in f or "secret" in f or "hash" in f]
        assert not leaked, f"비밀번호로 보이는 칸이 있다: {leaked}"

    def test_scenario_ids_are_unique(self) -> None:
        ids = [s.scenario_id for s in STAFF]
        assert len(ids) == len(set(ids))

    def test_login_ids_are_unique(self) -> None:
        logins = [s.login_id for s in STAFF]
        assert len(logins) == len(set(logins)), "login_id 는 unique 다 (spec-medical.md staff 표)"


@pytest.mark.parametrize("staff", STAFF, ids=lambda s: s.scenario_id)
class TestEachRow:
    def test_login_id_follows_the_rule(self, staff: Staff) -> None:
        assert LOGIN_ID_PATTERN.match(staff.login_id), (
            f"{staff.login_id!r} 이 ^[a-z0-9]{{4,}}$ 를 벗어난다 — 생성 후 바꿀 수 없는 값이다"
        )

    def test_roles_are_known_and_not_empty(self, staff: Staff) -> None:
        """빈 배열은 저장할 수 없다 — 서버에서 막는 규칙이다."""
        assert staff.roles, f"{staff.scenario_id} 의 roles 가 비어 있다"
        assert staff.roles <= KNOWN_ROLES, f"모르는 역할: {sorted(staff.roles - KNOWN_ROLES)}"

    def test_first_login_has_never_logged_in(self, staff: Staff) -> None:
        """must_change_password 는 「아직 한 번도 안 들어왔다」는 뜻이다."""
        if staff.must_change_password:
            assert not staff.last_login_at, f"{staff.scenario_id} 첫 로그인인데 마지막 로그인 기록이 있다"

    def test_left_at_matches_status(self, staff: Staff) -> None:
        if staff.status == "left":
            assert staff.left_at, f"{staff.scenario_id} 퇴사인데 퇴사일이 없다"
        else:
            assert not staff.left_at, f"{staff.scenario_id} 재직인데 퇴사일이 있다"

    def test_intent_is_written(self, staff: Staff) -> None:
        """왜 이 계정이 있는지 적혀 있어야 나중에 지워도 되는지 판단할 수 있다."""
        assert staff.intent.strip(), f"{staff.scenario_id} 에 케이스 의도가 없다"


class TestCoverage:
    def test_every_role_combination_exists(self) -> None:
        """KEY-23 매트릭스가 7가지 조합을 검사한다. 계정도 7가지가 다 있어야 한다."""
        have = {s.roles for s in STAFF}
        missing = ALL_COMBINATIONS - have
        assert not missing, f"계정이 없는 조합: {sorted(sorted(c) for c in missing)}"

    def test_the_blocked_case_exists(self) -> None:
        """KEY-9 인수조건 — 관리자+스탭이 의료 승인을 못 한다.

        그 조합의 계정이 없으면 검사할 대상이 없다.
        """
        s = by_id("SYN-STAFF-06")
        assert s.roles == {"staff", "admin"}
        assert s.is_active and not s.must_change_password, (
            "이 계정은 다른 이유로 막히면 안 된다 — 역할만으로 막혀야 한다"
        )

    def test_first_login_and_left_both_exist(self) -> None:
        assert any(s.must_change_password for s in STAFF), "L-3 을 볼 계정이 없다"
        assert any(s.status == "left" for s in STAFF), "퇴사자 차단을 볼 계정이 없다"

    def test_two_doctors_exist(self) -> None:
        """D2-3 본인 소유 처방 세트 — 남의 것을 못 고치는지 보려면 둘이 필요하다."""
        doctors = [s for s in STAFF if "doctor" in s.roles and s.is_active and not s.must_change_password]
        assert len(doctors) >= 2, "평범한 의사 계정이 둘은 있어야 소유자 검사를 볼 수 있다"

    def test_patient_csv_doctors_have_accounts(self) -> None:
        """환자 CSV의 담당의가 계정으로 존재해야 시드가 이어 붙는다."""
        names = {s.name for s in STAFF if "doctor" in s.roles}
        assert {"박연", "김연우"} <= names, f"환자 CSV 담당의의 계정이 없다: {sorted({'박연', '김연우'} - names)}"


class TestLockAccountIsReserved:
    """로그인 실패 카운터는 계정이 아니라 입력된 아이디 문자열에 붙는다.

    (`docs/auth-contract.md` 3절 — 없는 아이디도 똑같이 세야 존재 여부가 안 새어 나간다)

    그래서 잠금 시험이 다른 시험과 계정을 나눠 쓰면 순서에 따라 결과가 달라진다.
    """

    def test_the_lock_account_is_marked(self) -> None:
        s = by_login("lock01")
        assert "잠금" in s.intent, "잠금 전용 계정이라는 표시가 케이스 의도에 있어야 한다"

    def test_the_lock_account_is_otherwise_ordinary(self) -> None:
        """잠금 말고 다른 이유로 막히면 무엇 때문에 막혔는지 알 수 없다."""
        s = by_login("lock01")
        assert s.is_active and not s.must_change_password

    def test_no_other_test_should_pick_it_by_accident(self) -> None:
        """with_roles('staff') 가 lock01 을 집어 오면 안 된다 — 앞에 다른 계정이 있어야 한다."""
        assert with_roles("staff").login_id != "lock01"


class TestLookups:
    def test_by_id_and_by_login_agree(self) -> None:
        assert by_id("SYN-STAFF-01") is by_login("staff01")

    def test_missing_lookups_raise(self) -> None:
        with pytest.raises(KeyError):
            by_id("SYN-STAFF-99")
        with pytest.raises(KeyError):
            by_login("nobody")

    def test_role_separator_is_not_a_comma(self) -> None:
        """쉼표를 쓰면 CSV 칸이 쪼개진다."""
        assert ROLE_SEPARATOR != ","
