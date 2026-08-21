"""합성 직원 계정이 앞뒤가 맞는가 — DB도 서버도 필요 없다.

KEY-10. CSV를 고치다 어긋나면 여기서 걸린다.
`KEY-24` 통합 테스트가 이 계정들을 믿고 쓰므로, 픽스처가 먼저 성해야 한다.
"""

import csv
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.core import config
from app.core.config import Env
from app.tests.fixtures.staff import (
    CSV_PATH,
    DEFAULT_HOSPITAL,
    KNOWN_HOSPITALS,
    RESERVED_LOGIN_IDS,
    ROLE_SEPARATOR,
    ProductionFixtureError,
    Staff,
    StaffDataError,
    admins_besides,
    all_staff,
    by_id,
    by_login,
    in_hospital,
    with_roles,
)
from app.tests.rbac.matrix import VALID_COMBINATIONS, Role

LOGIN_ID_PATTERN = re.compile(r"^[a-z0-9]{4,}$")  # spec-medical.md staff 표

SOURCE = CSV_PATH.read_text(encoding="utf-8-sig")


@contextmanager
def using_csv(tmp_path: Path, text: str) -> Iterator[None]:
    """정본 대신 이 내용을 읽게 한다.

    캐시도 같이 비운다 — 안 그러면 앞 검사가 읽어 둔 정상 데이터가 그대로 돌아온다.
    """
    import app.tests.fixtures.staff as module

    path = tmp_path / "staff.csv"
    path.write_text(text, encoding="utf-8")

    original = module.CSV_PATH
    module.CSV_PATH = path
    module.forget_cached_staff()
    try:
        yield
    finally:
        module.CSV_PATH = original
        module.forget_cached_staff()


def load_broken(tmp_path: Path, text: str) -> str:
    """망가뜨린 CSV 를 읽혀 보고 오류 문구를 돌려준다."""
    with using_csv(tmp_path, text), pytest.raises(StaffDataError) as caught:
        all_staff()
    return str(caught.value)


def only(login_id: str) -> str:
    """그 계정 한 줄만 남긴 CSV.

    `with_roles` 가 예약 계정을 거르는지 보려면 **그 계정 말고는 후보가 없는**
    상태를 만들어야 한다. 정본 순서에 기대면, 앞에 다른 계정이 있어서 우연히
    안 걸리는 것을 「가드가 있다」로 잘못 읽는다.
    """
    lines = SOURCE.splitlines()
    # 칸 번호를 박아 두면 칸이 하나 늘 때마다 조용히 엉뚱한 칸을 본다.
    # 실제로 「병원」 칸이 앞에 들어오면서 한 번 깨졌다 — 머리글에서 찾는다.
    where = lines[0].split(",").index("login_id")
    picked = [line for line in lines[1:] if line.split(",")[where] == login_id]
    assert picked, f"그런 아이디가 CSV 에 없다: {login_id}"
    return "\n".join([lines[0], *picked]) + "\n"


#: 역할과 조합은 `matrix.py` 가 갖는다. 손으로 다시 적으면 KEY-23 이 조합을
#: 늘렸을 때 여기만 옛날 것으로 남는다 — 그러면 새 조합에 계정이 없어도 통과한다.
KNOWN_ROLES: frozenset[str] = frozenset(str(r) for r in Role)
ALL_COMBINATIONS: frozenset[frozenset[str]] = frozenset(frozenset(str(r) for r in c) for c in VALID_COMBINATIONS)


def rows() -> tuple[Staff, ...]:
    """`parametrize` 가 쓸 목록.

    CSV 가 깨져도 **수집은 되게** 한다. 여기서 예외가 나가면 이 파일뿐 아니라
    다른 검사까지 수집 단계에서 죽어, 정작 무엇이 틀렸는지가 안 남는다.
    깨진 사실은 `test_the_csv_loads` 가 평범한 실패로 알려 준다.
    """
    try:
        return all_staff()
    except StaffDataError:
        return ()


class TestFileIsSane:
    def test_the_csv_loads(self) -> None:
        """CSV 가 깨졌다면 **여기 하나만** 빨갛게 뜬다."""
        assert all_staff(), "직원 CSV가 비어 있다"

    def test_no_password_column(self) -> None:
        """AGENTS.md — 비밀번호를 커밋에 남기지 않는다.

        시드가 SEED_STAFF_PASSWORD 에서 받는다. 저장소에는 없다.
        """
        fields = {f for f in Staff.__dataclass_fields__ if f != "must_change_password"}
        leaked = [f for f in fields if "password" in f or "secret" in f or "hash" in f]
        assert not leaked, f"비밀번호로 보이는 칸이 있다: {leaked}"

    def test_scenario_ids_are_unique(self) -> None:
        ids = [s.scenario_id for s in all_staff()]
        assert len(ids) == len(set(ids))

    def test_login_ids_are_unique(self) -> None:
        logins = [s.login_id for s in all_staff()]
        assert len(logins) == len(set(logins)), "login_id 는 unique 다 (spec-medical.md staff 표)"


class TestBrokenRowsAreCaught:
    """조용히 잘못 읽히는 것이 제일 나쁘다 — 값이 그럴듯해서 안 보인다."""

    def test_a_stray_comma_shifts_the_columns(self, tmp_path: Path) -> None:
        """케이스 의도에 따옴표 없이 쉼표를 쓰면 그 행부터 칸이 밀린다."""
        broken = SOURCE.replace("기준 스탭 — L-1 로그인의 표준 계정", "기준 스탭, L-1 로그인의 표준 계정")
        assert "쉼표" in load_broken(tmp_path, broken)

    def test_a_typo_in_must_change_password(self, tmp_path: Path) -> None:
        """`y` 가 조용히 False 로 읽히면 첫 로그인 계정이 평범한 계정이 된다 —
        L-3 검사가 아무것도 안 보고 통과한다."""
        broken = SOURCE.replace(",Y,active,,,★ 첫 로그인", ",y,active,,,★ 첫 로그인")
        assert "must_change_password" in load_broken(tmp_path, broken)

    def test_a_typo_in_hospital(self, tmp_path: Path) -> None:
        broken = SOURCE.replace(",H1,staff01,", ",h1,staff01,")
        assert "병원" in load_broken(tmp_path, broken)

    def test_a_typo_in_status(self, tmp_path: Path) -> None:
        """`Left` 가 재직으로 읽히면 퇴사자 차단 검사가 산 사람을 본다."""
        broken = SOURCE.replace(",N,left,", ",N,Left,")
        assert "status" in load_broken(tmp_path, broken)


@pytest.mark.parametrize("staff", rows(), ids=lambda s: s.scenario_id)
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
        assert staff.intent, f"{staff.scenario_id} 에 케이스 의도가 없다"


class TestCoverage:
    def test_every_role_combination_exists(self) -> None:
        """KEY-23 매트릭스가 검사하는 조합마다 계정이 있어야 한다.

        조합 목록을 `matrix.py` 에서 받아 오므로, 거기서 조합이 늘면 여기가 먼저 운다.
        """
        have = {s.roles for s in all_staff()}
        missing = ALL_COMBINATIONS - have
        assert not missing, f"계정이 없는 조합: {sorted(sorted(c) for c in missing)}"

    def test_the_blocked_case_exists(self) -> None:
        """KEY-9 인수조건 — 관리자+스탭이 의료 승인을 못 한다."""
        s = by_id("SYN-STAFF-06")
        assert s.roles == {Role.STAFF, Role.ADMIN}
        assert s.is_ordinary, "이 계정은 다른 이유로 막히면 안 된다 — 역할만으로 막혀야 한다"

    def test_admin_does_not_get_in_the_way_of_a_doctor(self) -> None:
        """SYN-STAFF-07 의 반대쪽 — admin 이 승인을 **방해하지 않는다.**

        차단 조건이 나중에 「admin 을 가지면 승인 불가」로 넓어지면
        `SYN-STAFF-06` 은 그대로 통과하고 이쪽만 무너진다. 짝으로 둔다.
        """
        s = by_id("SYN-STAFF-07")
        assert s.roles == {Role.DOCTOR, Role.ADMIN}
        assert s.is_ordinary
        assert Role.DOCTOR in s.roles, "승인은 doctor 가 있으면 된다 — admin 이 그것을 빼앗지 않는다"

    def test_first_login_and_left_both_exist(self) -> None:
        assert any(s.must_change_password for s in all_staff()), "L-3 을 볼 계정이 없다"
        assert any(s.status == "left" for s in all_staff()), "퇴사자 차단을 볼 계정이 없다"

    def test_two_doctors_exist(self) -> None:
        """D2-3 본인 소유 처방 세트 — 남의 것을 못 고치는지 보려면 둘이 필요하다."""
        doctors = [s for s in all_staff() if Role.DOCTOR in s.roles and s.is_ordinary]
        assert len(doctors) >= 2, "평범한 의사 계정이 둘은 있어야 소유자 검사를 볼 수 있다"

    def test_patient_csv_doctors_have_accounts(self) -> None:
        """환자 CSV의 담당의가 계정으로 존재해야 시드가 이어 붙는다."""
        names = {s.name for s in all_staff() if Role.DOCTOR in s.roles}
        assert {"박연", "김연우"} <= names, f"환자 CSV 담당의의 계정이 없다: {sorted({'박연', '김연우'} - names)}"

    def test_the_retired_doctor_is_actually_on_a_past_visit(self) -> None:
        """SYN-STAFF-12 는 「지난 진료의 담당의로 이름이 남는다」가 의도다.

        환자 CSV 어디에도 담당의로 안 나오면 그 상황을 만들 데이터가 없어서
        시나리오가 글로만 남는다.
        """
        retired = by_id("SYN-STAFF-12")
        patients = CSV_PATH.parent / "synthetic-patients.csv"
        with patients.open(encoding="utf-8-sig") as f:
            visits = [r for r in csv.DictReader(f) if r["담당의"] == retired.name]

        assert visits, f"{retired.name}({retired.login_id}) 가 담당의인 진료가 환자 CSV 에 없다"
        assert all(v["진료일"] < retired.left_at[:10] for v in visits), (
            "퇴사 뒤 날짜의 진료를 맡고 있다 — 퇴사한 사람이 새 진료를 볼 수는 없다"
        )


class TestReservedAccounts:
    """이름을 대고 불러야만 오는 계정들.

    `lock01` 은 로그인 실패 카운터가 **입력된 아이디 문자열**에 붙어서
    (`docs/api/hospital.md` 3절), 다른 시험과 나눠 쓰면 순서에 따라 결과가 달라진다.
    `lastadmin01` 은 「마지막 관리자」 시나리오 전용이다.
    """

    @pytest.mark.parametrize("login_id", sorted(RESERVED_LOGIN_IDS))
    def test_it_exists_and_is_otherwise_ordinary(self, login_id: str) -> None:
        """예약 계정이 다른 이유로 막히면 무엇 때문에 막혔는지 알 수 없다."""
        s = by_login(login_id)
        assert s.is_ordinary
        assert s.is_reserved

    @pytest.mark.parametrize("login_id", sorted(RESERVED_LOGIN_IDS))
    def test_with_roles_never_hands_it_out(self, login_id: str, tmp_path: Path) -> None:
        """**그 계정 말고 후보가 없을 때도** 안 준다.

        정본 순서로만 확인하면 앞에 다른 계정이 있어서 우연히 안 걸리는 것을
        「가드가 있다」로 잘못 읽는다 — 앞 행이 바뀌면 조용히 집혀 온다.
        후보를 하나로 줄여 놓고, 그래도 거절하는지 본다.
        """
        roles = by_login(login_id).roles

        with using_csv(tmp_path, only(login_id)):
            assert all_staff()[0].login_id == login_id  # 후보가 이 하나뿐인 상태
            with pytest.raises(KeyError):
                with_roles(*roles)

    def test_the_lock_account_says_so(self) -> None:
        assert "잠금" in by_login("lock01").intent, "잠금 전용이라는 표시가 케이스 의도에 있어야 한다"


class TestLastAdminScenarioIsHonest:
    """「마지막 관리자」는 이 픽스처만으로는 성립하지 않는다.

    admin 을 가진 재직자가 여럿이라, `lastadmin01` 에서 admin 을 빼는 저장은
    아무 규칙에도 안 걸린다. 그걸 모르고 검사를 짜면 **다른 이유로 통과하거나
    실패한다.** 그 사실을 여기서 못 박아 둔다.
    """

    def test_there_is_more_than_one_admin(self) -> None:
        others = admins_besides("lastadmin01")
        assert others, "admin 이 하나뿐이면 이 검사는 필요 없다 — 아래 안내도 지운다"

    def test_the_scenario_needs_the_others_removed_first(self) -> None:
        """KEY-24 가 이 시나리오를 짤 때 무엇을 먼저 치워야 하는지 알려 준다."""
        others = admins_besides("lastadmin01")
        assert by_login("lastadmin01") not in others
        assert all(Role.ADMIN in s.roles and s.is_active for s in others)

    def test_the_intent_says_what_it_is_for(self) -> None:
        assert "마지막 관리자" in by_login("lastadmin01").intent


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


class TestHospitalIsolation:
    """의원이 둘 있어야 「타 병원 자료가 안 보인다」를 검사할 수 있다.

    `docs/api/hospital.md` 환자·진료 5절 — 타 병원 리소스는 `403` 이
    아니라 `404` 다. 존재 여부 자체를 감춘다. 그걸 확인하려면 **남의 의원
    사람**이 있어야 하는데, 예전에는 이 픽스처에 의원이 하나뿐이었다.
    """

    def test_both_hospitals_have_people(self) -> None:
        for hospital in KNOWN_HOSPITALS:
            assert in_hospital(hospital), f"{hospital} 에 아무도 없다 — 격리 검사의 한쪽이 빈다"

    def test_the_other_hospital_has_all_three_roles(self) -> None:
        """스탭 · 의사 · 관리자가 다 있어야 역할별로 막히는지 볼 수 있다."""
        others = in_hospital("H2")
        covered = {role for s in others for role in s.roles}
        assert covered == {"staff", "doctor", "admin"}, f"H2 에 없는 역할이 있다: {covered}"

    def test_with_roles_stays_in_the_asked_hospital(self) -> None:
        assert with_roles("staff").hospital == DEFAULT_HOSPITAL
        assert with_roles("staff", hospital="H2").hospital == "H2"
        assert with_roles("staff").login_id != with_roles("staff", hospital="H2").login_id

    def test_asking_for_an_unknown_hospital_raises(self) -> None:
        with pytest.raises(KeyError):
            in_hospital("H9")

    def test_a_name_is_not_enough_to_find_a_doctor(self) -> None:
        """두 의원에 같은 이름의 의사가 있다.

        `app/tests/fixtures/mapping.py` 는 담당의를 「이름 → 직원 픽스처로
        푼다」고 적어 두었다. 이름만 보고 풀면 **남의 의원 의사**를 집는다.
        그 상황을 실제로 만들 수 있어야 그 코드를 검사할 수 있다.
        """
        same_name = [s for s in all_staff() if s.name == "박연"]
        assert len(same_name) == 2, "동명이인 의사가 사라졌다 — 이름만으로 푸는 코드를 못 잡는다"
        assert {s.hospital for s in same_name} == {"H1", "H2"}
        assert len({s.login_id for s in same_name}) == 2


class TestLastAdminIsPerHospital:
    """「마지막 관리자」는 의원 단위 규칙이다.

    옆 의원에 관리자가 있다고 이 의원이 관리자 없이 남아도 되는 것이 아니다.
    """

    def test_it_does_not_count_the_other_hospital(self) -> None:
        others = admins_besides("lastadmin01")
        assert others, "H1 에 다른 관리자가 없으면 이 검사가 뜻이 없다"
        assert all(s.hospital == "H1" for s in others), [s.login_id for s in others]

    def test_the_other_hospital_admin_exists_but_is_not_counted(self) -> None:
        elsewhere = [s for s in in_hospital("H2") if "admin" in s.roles]
        assert elsewhere, "H2 에 관리자가 없으면 이 검사가 헛돈다"
        assert not {s.login_id for s in elsewhere} & {s.login_id for s in admins_besides("lastadmin01")}


class TestNeverRunsInProduction:
    """합성 계정을 운영에서 읽으려 하면 멈춘다.

    이 CSV 에는 비밀번호가 없어서 읽는 것만으로는 로그인이 생기지 않는다.
    막으려는 것은 이것을 읽어 DB 에 넣는 **시드**다 — 합성 계정이 운영 DB 에
    들어가면 `SEED_STAFF_PASSWORD` 를 아는 사람이 실제로 들어올 수 있다.

    `#33`(KEY-36) 이 같은 가드를 먼저 만들었는데 `APP_ENV` 를 보고 있었다.
    저장소가 쓰는 이름은 `ENV` 라, 운영에서 값이 비어 기본값 `local` 로 읽혀
    **가드가 있는 채로 아무것도 막지 않았다.** 이름을 맞추는 것이 이 검사의 핵심이다.
    """

    def _with_env(self, env: Env):
        import contextlib

        @contextlib.contextmanager
        def ctx():
            import app.tests.fixtures.staff as module

            before = config.ENV
            config.ENV = env
            module.forget_cached_staff()
            try:
                yield
            finally:
                config.ENV = before
                module.forget_cached_staff()

        return ctx()

    def test_production_is_refused(self) -> None:
        with self._with_env(Env.PROD), pytest.raises(ProductionFixtureError):
            all_staff()

    def test_local_and_dev_still_work(self) -> None:
        for env in (Env.LOCAL, Env.DEV):
            with self._with_env(env):
                assert all_staff(), f"{env} 에서 픽스처를 못 읽는다"

    def test_it_reads_the_name_the_repository_actually_uses(self) -> None:
        """`ENV` 가 아니라 `APP_ENV` 같은 다른 이름을 보면, 운영에서 값이
        비어 기본값으로 읽히고 가드가 조용히 통과한다."""
        import os

        before = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "prod"
        try:
            with self._with_env(Env.LOCAL):
                assert all_staff(), "APP_ENV 를 보고 있다 — 저장소가 쓰는 이름은 ENV 다"
        finally:
            if before is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = before

    def test_config_really_reads_env_not_app_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """위 검사는 `config.ENV` 를 직접 넣어 확인한다 — pydantic 이 환경변수를
        어떻게 읽는지는 안 거친다. 그래서 `ENV` 필드에 `APP_ENV` alias 가
        붙는 식으로 같은 실수가 아래층에서 나도 위 검사는 계속 통과한다(`#45` 리뷰).

        여기서는 `Config()` 를 실제로 새로 만들어, **읽는 이름 자체**를 잰다.
        """
        from app.core.config import Config

        monkeypatch.setenv("ENV", "prod")
        monkeypatch.delenv("APP_ENV", raising=False)
        assert Config().ENV is Env.PROD, "`ENV` 를 안 읽는다 — 운영에서 기본값 local 로 통과한다"

        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("APP_ENV", "prod")
        assert Config().ENV is Env.LOCAL, "`APP_ENV` 를 읽고 있다 — 저장소가 쓰는 이름이 아니다"

    def test_guard_still_bites_after_the_csv_was_already_read(self) -> None:
        """**이 검사가 이 PR 의 이유다.**

        가드가 `@cache` 안에 있으면 한 번 성공한 뒤로는 본문이 아예 안 돌아서,
        `ENV` 가 `prod` 로 바뀌어도 읽어 둔 계정이 그대로 나온다. 캐시를 비우는
        `_with_env` 를 안 쓰고 **실제로 그 상황을 만들어** 잰다 —
        `cache_clear()` 를 챙기는 검사만 있으면 이 갈래는 영원히 안 지나간다.
        """
        before = config.ENV
        try:
            config.ENV = Env.LOCAL
            assert all_staff(), "먼저 한 번 읽어 캐시를 채운다"

            config.ENV = Env.PROD  # 캐시는 그대로 둔다
            with pytest.raises(ProductionFixtureError):
                all_staff()
        finally:
            config.ENV = before
