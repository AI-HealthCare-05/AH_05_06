"""아이디가 **의원 안에서만** 유일하다 — KEY-324.

전에는 `login_id` 가 전 시스템에서 유일했다. 로그인이 `{아이디, 비밀번호}` 둘만
받아 병원을 알 수 없었기 때문이다(KEY-26 §4). 그 전역 유일이 둘을 낳았다.

  ① **남의 의원 아이디를 알아낼 수 있었다** — 관리자가 아이디를 하나씩 넣어 보면
     다른 의원이 쓰는 것에서 `409` 가 났다.
  ② **짧은 아이디를 나눠 쓸 수 없었다** — 두 의원이 다 `reception` 을 쓰고
     싶어도 둘째 의원은 못 만든다.

이제 로그인이 **의원 코드를 함께 받는다**. 병원을 먼저 알고 나서 아이디를 찾으므로
유일성을 의원 안으로 좁힐 수 있다.

여기서 재는 것은 인수조건 1~4 다. 5(이관)는 `app/tests/migrations` 가, 6(회귀)은
기존 로그인·세션·비밀번호 검사가 그대로 잰다.
"""

from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.exceptions import IntegrityError

from app.core.utils.security import hash_password
from app.main import app
from app.models.staffs import Hospital, Staff, default_clinic_code
from app.tests.auth_base import PASSWORD, AuthTestCase

LOGIN_URL = "/api/v1/auth/login"


def migration_source() -> str:
    """이관 마이그레이션을 **쓰인 그대로** 읽는다."""
    return next(Path("app/core/db/migrations/models").glob("*key324_clinic_scoped_login.py")).read_text(
        encoding="utf-8"
    )


class ClinicScopedLoginTestCase(AuthTestCase):
    """의원 둘 · 양쪽에 같은 아이디."""

    #: 의원 → 그 의원의 `reception` 직원 번호. 「어느 의원에 들어왔나」를 이것으로 잰다.
    who: dict[int, int]

    async def two_clinics(self, login_id: str = "reception") -> tuple[Hospital, Hospital]:
        first = await Hospital.create(name="첫째의원", code="clinic0001")
        second = await Hospital.create(name="둘째의원", code="clinic0002")
        self.who = {}
        for hospital, name in ((first, "첫째접수"), (second, "둘째접수")):
            staff = await Staff.create(
                hospital=hospital,
                login_id=login_id,
                password_hash=hash_password(PASSWORD),
                name=name,
                roles=["staff"],
                must_change_password=False,
            )
            self.who[hospital.hospital_id] = staff.staff_id
        return first, second

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def login(self, clinic_code: str, login_id: str = "reception", password: str = PASSWORD):
        async with self.client() as http:
            return await http.post(
                LOGIN_URL, json={"clinic_code": clinic_code, "login_id": login_id, "password": password}
            )


class TestTwoClinicsCanShareAnId(ClinicScopedLoginTestCase):
    async def test_the_same_login_id_exists_in_both(self) -> None:
        """인수조건 1 — 전에는 둘째 의원이 아예 못 만들었다."""
        await self.two_clinics()

        assert await Staff.filter(login_id="reception").count() == 2


class TestEachOneLandsInItsOwnClinic(ClinicScopedLoginTestCase):
    async def test_the_code_decides_which_clinic(self) -> None:
        """인수조건 2 — 같은 아이디가 섞이지 않는다."""
        first, second = await self.two_clinics()

        async with self.client() as http:
            for hospital in (first, second):
                signed = await http.post(
                    LOGIN_URL,
                    json={"clinic_code": hospital.code, "login_id": "reception", "password": PASSWORD},
                )
                assert signed.status_code == 200, signed.text
                me = await http.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {signed.json()['access_token']}"},
                )
                assert me.status_code == 200, me.text
                #: `/auth/me` 는 의원 번호를 안 준다(계약 4절). **누가 들어왔는지**로
                #: 잰다 — 아이디는 같고 사람은 다르다.
                assert me.json()["id"] == self.who[hospital.hospital_id], (
                    f"{hospital.code} 로 들어왔는데 다른 의원 사람이 됐다 — {me.json()}"
                )

    async def test_a_wrong_code_looks_like_a_wrong_password(self) -> None:
        """**없는 의원도 없는 아이디와 같은 답을 받는다.**

        코드만 바꿔 가며 두드려 「그 의원이 있는가」를 알아낼 수 없어야 한다.
        """
        await self.two_clinics()

        missing_clinic = await self.login("clinic9999")
        missing_id = await self.login("clinic0001", login_id="nobody01")
        wrong_password = await self.login("clinic0001", password="Wrong-password-1!")

        codes = {response.status_code for response in (missing_clinic, missing_id, wrong_password)}
        assert codes == {401}, f"세 갈래가 다른 답을 준다 — {codes}"
        bodies = {response.json()["code"] for response in (missing_clinic, missing_id, wrong_password)}
        assert bodies == {"invalid_credentials"}, f"어느 쪽이 틀렸는지 말한다 — {bodies}"


class TestTheIdIsTakenOnlyInsideTheClinic(ClinicScopedLoginTestCase):
    async def test_another_clinic_using_it_does_not_block_creation(self) -> None:
        """인수조건 3 — `409` 가 제 의원 안에서만 난다."""
        first, second = await self.two_clinics(login_id="taken01")
        admin = await Staff.create(
            hospital=first,
            login_id="admin01",
            password_hash=hash_password(PASSWORD),
            name="관리자",
            roles=["admin"],
            must_change_password=False,
        )
        assert admin.hospital_id == first.hospital_id
        #: **옆 의원이 이미 쓰고 있다.** 이것을 미리 만들어 두지 않으면 아래
        #: `onlyother01` 은 아무도 안 쓰는 아이디라, `409` 가 의원을 가리든 말든
        #: `201` 이 나와 검사가 아무것도 안 잰다.
        await Staff.create(
            hospital=second,
            login_id="onlyother01",
            password_hash=hash_password(PASSWORD),
            name="옆집",
            roles=["staff"],
            must_change_password=False,
        )

        async with self.client() as http:
            signed = await http.post(
                LOGIN_URL, json={"clinic_code": first.code, "login_id": "admin01", "password": PASSWORD}
            )
            headers = {"Authorization": f"Bearer {signed.json()['access_token']}"}

            #: 제 의원이 이미 쓰는 아이디 → 409
            mine = await http.post(
                "/api/v1/admin/staffs",
                headers=headers,
                json={"login_id": "taken01", "name": "겹침", "roles": ["staff"], "password": PASSWORD},
            )
            #: 남의 의원만 쓰는 아이디 → 만들어진다
            theirs = await http.post(
                "/api/v1/admin/staffs",
                headers=headers,
                json={"login_id": "onlyother01", "name": "새사람", "roles": ["staff"], "password": PASSWORD},
            )

        assert mine.status_code == 409, mine.text
        assert mine.json()["code"] == "LOGIN_ID_TAKEN"
        assert theirs.status_code == 201, (
            f"옆 의원이 쓴다고 막혔다 — {theirs.status_code} {theirs.text}. "
            "아이디를 하나씩 넣어 보면 남의 의원에 무엇이 있는지 알아낼 수 있다"
        )
        assert await Staff.filter(login_id="onlyother01").count() == 2, "두 의원이 같은 아이디를 갖지 못했다"


class TestAnotherClinicsIdIsNotMistakenForADuplicate(ClinicScopedLoginTestCase):
    """중복이 **아닌** 잘못을 남의 의원 아이디 때문에 「아이디 중복」으로 부르지 않는다.

    `409` 는 `IntegrityError` 를 되물어 확인한 뒤에만 낸다 — 그러지 않던 때
    감사 기록의 NOT NULL 위반이 관리자 화면에 「이미 쓰고 있는 아이디입니다」로
    떴다(`#285`). KEY-324 는 그 되물음을 **제 의원 안으로** 좁혔다. 안 좁히면
    옆 의원이 쓰는 아이디 하나로 같은 오진이 되살아난다.
    """

    async def test_a_failure_elsewhere_keeps_its_own_name(self) -> None:
        first, second = await self.two_clinics(login_id="taken01")
        await Staff.create(
            hospital=first,
            login_id="admin01",
            password_hash=hash_password(PASSWORD),
            name="관리자",
            roles=["admin"],
            must_change_password=False,
        )
        #: **옆 의원만** 쓰는 아이디
        await Staff.create(
            hospital=second,
            login_id="onlyother01",
            password_hash=hash_password(PASSWORD),
            name="옆집",
            roles=["staff"],
            must_change_password=False,
        )

        async with self.client() as http:
            signed = await http.post(
                LOGIN_URL, json={"clinic_code": first.code, "login_id": "admin01", "password": PASSWORD}
            )
            headers = {"Authorization": f"Bearer {signed.json()['access_token']}"}

            #: 아이디와 **무관한** 잘못을 낸다 — 감사 기록 쪽이 넘어진 상황
            status: int | None = None
            with patch(
                "app.services.admin_staffs.StaffAccountEvent.create",
                side_effect=IntegrityError("감사 기록 NOT NULL"),
            ):
                try:
                    answer = await http.post(
                        "/api/v1/admin/staffs",
                        headers=headers,
                        json={
                            "login_id": "onlyother01",
                            "name": "새사람",
                            "roles": ["staff"],
                            "password": PASSWORD,
                        },
                    )
                except IntegrityError:
                    pass  #: 진짜 잘못이 **제 이름 그대로** 올라왔다 — 이게 맞다
                else:
                    status = answer.status_code

        assert status is None, (
            f"아이디 중복이 아닌데 {status} 로 덮였다 — 옆 의원이 그 아이디를 쓴다는 것 말고 이유가 없다. "
            "관리자는 아이디만 바꿔 가며 헤맨다"
        )


class TestTheLockIsPerClinic(ClinicScopedLoginTestCase):
    async def test_one_clinic_locking_does_not_lock_the_other(self) -> None:
        """인수조건 4 — 안 그러면 **남의 의원 계정을 임의로 잠글 수 있다.**"""
        first, second = await self.two_clinics()

        for _ in range(6):
            await self.login(first.code or "", password="Wrong-password-1!")

        locked = await self.login(first.code or "")
        other = await self.login(second.code or "")

        assert locked.status_code == 429, f"다섯 번 넘게 틀렸는데 안 잠겼다 — {locked.status_code}"
        assert other.status_code == 200, (
            f"옆 의원의 같은 아이디까지 잠겼다 — {other.status_code}. 남의 계정을 임의로 잠글 수 있다"
        )


class TestEveryClinicThatPeopleLogIntoHasACode:
    """코드가 없는 의원은 **로그인 대상이 아니다** — 조용히 다른 의원에 붙지 않는다.

    스키마로 강제하지는 않는다(검사 픽스처 92 자리가 코드 없이 의원을 만든다).
    대신 시드와 이관 마이그레이션이 **같은 규칙**으로 채운다 — 그 둘이 갈리면
    옮긴 뒤의 코드와 다시 시드한 뒤의 코드가 달라져, 어제 되던 로그인이 오늘
    안 된다.
    """

    def test_the_seed_and_the_migration_agree(self) -> None:
        migration = migration_source()

        assert "CONCAT('clinic', LPAD(`hospital_id`, 4, '0'))" in migration, (
            "이관이 코드를 안 채운다 — 옮긴 뒤 아무도 못 들어온다"
        )
        assert default_clinic_code(1) == "clinic0001", "규칙이 갈렸다"
        assert default_clinic_code(42) == "clinic0042", "규칙이 갈렸다"


class TestTheNewUniquenessIsInTheSchema:
    """유일성은 코드가 아니라 **DB 가** 지킨다 — 동시에 두 요청이 와도 막힌다."""

    def test_the_composite_index_goes_on_before_the_old_one_comes_off(self) -> None:
        """**순서가 중요하다.**

        옛 전역 유일을 먼저 떼면 합성 인덱스가 붙기 전까지 **아무 유일성도 없는
        틈**이 생긴다. 그 틈에 같은 의원 같은 아이디가 둘 들어오면, 그 뒤로
        그 의원 로그인은 누구를 고를지 모른다 — 그리고 인덱스도 못 붙는다.
        """
        migration = migration_source()

        added = migration.index("ALTER TABLE `staff` ADD UNIQUE INDEX `uid_staff_hospita")
        dropped = migration.index("ALTER TABLE `staff` DROP INDEX `login_id`")

        assert added < dropped, "옛 유일성을 먼저 뗀다 — 그 사이에 겹친 아이디가 들어올 수 있다"

    def test_the_index_covers_the_hospital_and_the_id(self) -> None:
        migration = migration_source()

        assert "`uid_staff_hospita_431a8a` (`hospital_id`, `login_id`)" in migration, (
            "합성 유일 인덱스가 둘을 다 안 덮는다"
        )
