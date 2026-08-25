"""`/auth/me` 와 비밀번호 변경 — KEY-73 (`docs/api/hospital.md` 2·4·5절).

비밀번호 변경은 **두 경우가 요청 조건이 다르고, 어느 쪽인지는 서버가 정한다.**
요청이 정하게 두면 최초 로그인이 아닌 사람도 `current_password` 를 빼고 보내면
확인 없이 바꿀 수 있다 — 그 자리를 검사로 못 박는다.
"""

from typing import Any

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.redis_client import get_redis
from app.core.utils.security import hash_password, verify_password
from app.main import app
from app.models.staffs import Hospital, Staff
from app.tests.fakes import FakeRedis

PASSWORD = "Password123!"
NEW_PASSWORD = "newpass1!"
BASE = "/api/v1/auth"


async def make_staff(login_id: str = "staff01", **kwargs: Any) -> Staff:
    hospital = await Hospital.create(name="여성의원")
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password(PASSWORD),
        name="한소영",
        **{"roles": ["staff"], "must_change_password": False, **kwargs},
    )


class PasswordTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis
        # 쿠키 도메인을 비워 둔다. `.env` 에 COOKIE_DOMAIN 이 박혀 있으면
        # 테스트 클라이언트의 호스트(`test`)와 안 맞아 **쿠키가 통째로 버려지고**,
        # rotation·로그아웃 검사가 전부 「쿠키가 없다」로 깨진다.
        # config.py 의 주석이 경고하는 그 상황이고, 실제로 로컬에서 났다.
        # 검사가 개발자 `.env` 에 좌우되면 안 된다.
        self._cookie_domain = config.COOKIE_DOMAIN
        config.COOKIE_DOMAIN = ""

    def tearDown(self) -> None:
        config.COOKIE_DOMAIN = self._cookie_domain
        app.dependency_overrides.clear()
        super().tearDown()

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def sign_in(self, client: AsyncClient, login_id: str = "staff01") -> dict[str, str]:
        response = await client.post(f"{BASE}/login", json={"login_id": login_id, "password": PASSWORD})
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestMe(PasswordTestCase):
    async def test_carries_what_the_screen_needs_to_branch(self) -> None:
        """`roles` 로 FE 가 초기 화면(S1/D1/A1)을 정하고, `clinic_name` 은 화면에 뜬다."""
        await make_staff(roles=["admin", "staff"])

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.get(f"{BASE}/me", headers=headers)

        body = response.json()
        assert response.status_code == 200
        assert body["login_id"] == "staff01"
        assert body["roles"] == ["admin", "staff"]
        assert body["clinic_name"] == "여성의원"
        assert body["must_change_password"] is False

    async def test_never_carries_the_password(self) -> None:
        """화면이 쓰지 않는 값을 보내면 새어 나갈 자리만 는다.

        `must_change_password` 는 화면이 쓰는 값이라 이름에 password 가 들어간다 —
        찾아야 하는 것은 **해시 자체**다.
        """
        staff = await make_staff()

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.get(f"{BASE}/me", headers=headers)

        assert staff.password_hash not in response.text
        assert "password_hash" not in response.text
        assert set(response.json()) == {
            "id",
            "name",
            "login_id",
            "roles",
            "must_change_password",
            "clinic_name",
        }

    async def test_needs_a_token(self) -> None:
        async with self.client() as client:
            response = await client.get(f"{BASE}/me")

        assert response.status_code == 401
        assert response.json()["code"] == "token_expired"

    async def test_first_login_can_still_read_me(self) -> None:
        """비밀번호를 바꾸기 전에도 자기 자신은 볼 수 있어야 한다 —
        화면이 「누구로 로그인했는지」를 알아야 L-3 을 그린다."""
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.get(f"{BASE}/me", headers=headers)

        assert response.status_code == 200
        assert response.json()["must_change_password"] is True


class TestFirstLoginChange(PasswordTestCase):
    async def test_new_password_alone_is_enough(self) -> None:
        """방금 그 비밀번호로 로그인했다. 한 화면에서 같은 값을 두 번 넣게 하면
        거기서부터 막힌다."""
        staff = await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(f"{BASE}/password", json={"new_password": NEW_PASSWORD}, headers=headers)

        await staff.refresh_from_db()
        assert response.status_code == 204
        assert staff.must_change_password is False
        assert staff.password_changed_at is not None
        assert verify_password(NEW_PASSWORD, staff.password_hash)

    async def test_current_password_is_ignored_not_rejected(self) -> None:
        """참인데 `current_password` 가 오면 무시한다(계약 4절)."""
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(
                f"{BASE}/password",
                json={"current_password": "완전히 틀린 값", "new_password": NEW_PASSWORD},
                headers=headers,
            )

        assert response.status_code == 204

    async def test_same_password_is_refused(self) -> None:
        """최초 변경의 이유가 「정해준 사람이 계속 알고 있다」라, 같은 값으로
        바꾸면 아무것도 달라지지 않는다."""
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(f"{BASE}/password", json={"new_password": PASSWORD}, headers=headers)

        assert response.status_code == 422


class TestNormalChange(PasswordTestCase):
    async def test_current_password_is_required(self) -> None:
        """거짓인데 없으면 422. 자리를 비운 사이 남이 바꾸는 것을 막는다."""
        await make_staff()

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(f"{BASE}/password", json={"new_password": NEW_PASSWORD}, headers=headers)

        assert response.status_code == 422

    async def test_wrong_current_password_is_refused(self) -> None:
        staff = await make_staff()

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(
                f"{BASE}/password",
                json={"current_password": "WrongPass1!", "new_password": NEW_PASSWORD},
                headers=headers,
            )

        await staff.refresh_from_db()
        assert response.status_code == 422
        assert verify_password(PASSWORD, staff.password_hash)

    async def test_right_current_password_changes_it(self) -> None:
        staff = await make_staff()

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(
                f"{BASE}/password",
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                headers=headers,
            )

        await staff.refresh_from_db()
        assert response.status_code == 204
        assert verify_password(NEW_PASSWORD, staff.password_hash)


class TestPasswordRules(PasswordTestCase):
    async def test_screen_rule_and_server_rule_agree(self) -> None:
        """화면이 약속하는 것은 「영문 · 숫자 · 기호를 섞어 8자 이상」이다.

        기존 `validate_password` 는 **대문자를 따로 요구**해서 `abcd1234!` 를
        거부한다 — 화면대로 만든 비밀번호가 서버에서 막히면 사용자는 무엇이
        틀렸는지 알 수 없다.
        """
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(f"{BASE}/password", json={"new_password": "abcd1234!"}, headers=headers)

        assert response.status_code == 204

    async def test_missing_a_kind_is_refused(self) -> None:
        await make_staff(must_change_password=True)
        weak = ["short1!", "onlyletters!", "12345678!", "abcd1234"]

        async with self.client() as client:
            headers = await self.sign_in(client)
            for password in weak:
                response = await client.patch(f"{BASE}/password", json={"new_password": password}, headers=headers)
                assert response.status_code == 422, password


class TestSessionsAfterChange(PasswordTestCase):
    async def test_every_session_dies(self) -> None:
        """바꾸는 이유가 「남이 알고 있다」이므로 그 남의 세션도 같이 끊는다."""
        await make_staff()

        async with self.client() as desk, self.client() as room:
            await self.sign_in(desk)
            await self.sign_in(room)
            headers = await self.sign_in(desk)

            await desk.patch(
                f"{BASE}/password",
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                headers=headers,
            )

            mine = await desk.post(f"{BASE}/refresh")
            theirs = await room.post(f"{BASE}/refresh")

        assert mine.status_code == 401
        assert theirs.status_code == 401

    async def test_cookie_is_cleared(self) -> None:
        """죽은 토큰을 계속 들고 다니지 않게 한다."""
        await make_staff()

        async with self.client() as client:
            headers = await self.sign_in(client)
            response = await client.patch(
                f"{BASE}/password",
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                headers=headers,
            )

        cookie = next(h for h in response.headers.get_list("set-cookie") if "refresh_token=" in h)
        assert 'refresh_token=""' in cookie or "refresh_token=;" in cookie

    async def test_new_password_works_right_away(self) -> None:
        await make_staff()

        async with self.client() as client:
            headers = await self.sign_in(client)
            await client.patch(
                f"{BASE}/password",
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                headers=headers,
            )

            again = await client.post(f"{BASE}/login", json={"login_id": "staff01", "password": NEW_PASSWORD})

        assert again.status_code == 200
        assert again.json()["must_change_password"] is False


class TestPasswordGateBlocksEverythingElse(PasswordTestCase):
    async def test_other_protected_paths_are_403(self) -> None:
        """「최초 로그인 사용자는 L-3 완료 전 다른 보호 화면에 접근할 수 없음」.

        예외는 자기 자신을 벗어나지 않는 셋뿐이다.

        예전에는 `/users/me` 로 쟀는데, 그 경로는 옛 `User` 계약이라 **관문이
        아니라 그 앞에서** 막혔다. 검사 자신이 「통과되지 않는다만 본다」고
        적어 둔 그대로, 관문을 통째로 들어내도 통과하는 검사였다.

        `/users/me` 를 지우면서(KEY-167) **실제 보호 경로**로 옮긴다. 이제
        관문이 내는 `password_change_required` 를 직접 확인한다.
        """
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            blocked = await client.get("/api/v1/patients", headers=headers)

        assert blocked.status_code == 403, f"관문이 열려 있다: {blocked.status_code}"
        assert blocked.json()["code"] == "password_change_required"

    async def test_the_way_out_stays_open(self) -> None:
        """**막기만 하면 갇힌다.** 비밀번호를 바꾸러 갈 길은 열려 있어야 한다.

        관문을 「전부 403」으로 만들면 이 검사가 죽는다 — 그러면 최초 로그인
        사용자는 아무것도 못 하고 로그인만 반복하게 된다.
        """
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            me = await client.get(f"{BASE}/me", headers=headers)
            change = await client.patch(f"{BASE}/password", json={"new_password": NEW_PASSWORD}, headers=headers)

        assert me.status_code == 200, "자기 정보 조회가 막히면 화면이 이름조차 못 띄운다"
        assert change.status_code == 204, "비밀번호를 바꿀 길이 막혔다 — 나갈 수 없다"

    async def test_gate_lifts_after_the_change(self) -> None:
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            await client.patch(f"{BASE}/password", json={"new_password": NEW_PASSWORD}, headers=headers)

            again = await client.post(f"{BASE}/login", json={"login_id": "staff01", "password": NEW_PASSWORD})
            fresh = {"Authorization": f"Bearer {again.json()['access_token']}"}
            response = await client.get(f"{BASE}/me", headers=fresh)

        assert response.json()["must_change_password"] is False


class TestGateExemptionLivesWithTheRoute(PasswordTestCase):
    """관문 예외를 **경로가 스스로** 밝힌다.

    예전에는 예외 경로 목록이 `dependencies/staff_auth.py` 에 문자열로 박혀
    있었다. 경로를 옮기거나 이름을 바꾸면 목록만 옛것으로 남는데, 그러면 둘 중
    하나가 조용히 일어난다 — 비밀번호를 바꿀 길이 막혀 계정이 잠기거나,
    반대로 관문이 뚫린다.
    """

    def _exempt_paths(self) -> set[str]:
        from app.dependencies.staff_auth import PASSWORD_GATE_EXEMPT_KEY

        return {
            str(getattr(route, "path", ""))
            for route in app.routes
            if (getattr(route, "openapi_extra", None) or {}).get(PASSWORD_GATE_EXEMPT_KEY)
        }

    async def test_exactly_the_three_paths_are_marked(self) -> None:
        assert self._exempt_paths() == {
            "/api/v1/auth/me",
            "/api/v1/auth/password",
            "/api/v1/auth/logout",
        }

    async def test_the_marked_paths_are_reachable_before_the_change(self) -> None:
        """표시가 실제로 읽히는가 — 세 곳 다 첫 로그인 상태에서 열려야 한다."""
        await make_staff(must_change_password=True)

        async with self.client() as client:
            headers = await self.sign_in(client)
            me = await client.get(f"{BASE}/me", headers=headers)
            out = await client.post(f"{BASE}/logout", headers=headers)

        assert me.status_code == 200
        assert out.status_code == 204

    async def test_a_route_without_the_mark_is_not_exempt(self) -> None:
        """표시가 없으면 예외가 아니다.

        이 브랜치에는 관문을 쓰면서 표시가 없는 경로가 아직 없어서(보호 API 가
        `KEY-34`·`KEY-60` 쪽에 있다) 판정 자체를 본다. 표시를 안 읽고 늘 통과시키면
        여기서 걸린다.
        """
        from types import SimpleNamespace

        from app.dependencies.staff_auth import _is_password_gate_exempt

        plain = SimpleNamespace(scope={"route": SimpleNamespace(openapi_extra=None)})
        other = SimpleNamespace(scope={"route": SimpleNamespace(openapi_extra={"x-something-else": True})})
        nothing = SimpleNamespace(scope={})

        assert not _is_password_gate_exempt(plain)  # type: ignore[arg-type]
        assert not _is_password_gate_exempt(other)  # type: ignore[arg-type]
        assert not _is_password_gate_exempt(nothing)  # type: ignore[arg-type]
