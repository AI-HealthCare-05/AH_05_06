"""세션이 계약대로 도는지 본다 — KEY-73 (`docs/auth-contract.md` 4·5절).

rotation · 유휴 30분 · 로그아웃 · 재사용 감지가 서로 얽혀 있어서, 하나를
고치면 다른 하나가 조용히 깨진다. 그 자리를 검사로 못 박는다.
"""

from typing import Any

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.staffs import Hospital, Staff, StaffStatus
from app.tests.fakes import FakeRedis

PASSWORD = "Password123!"
BASE = "/api/v1/auth"
REFRESH_PATH = "/api/v1/auth"


async def make_staff(login_id: str = "staff01", **kwargs: Any) -> Staff:
    hospital = await Hospital.create(name="여성의원")
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password(PASSWORD),
        name="한소영",
        roles=["staff"],
        **{"must_change_password": False, **kwargs},
    )


class SessionTestCase(TestCase):
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

    async def sign_in(self, client: AsyncClient, login_id: str = "staff01", remember: bool = False) -> str:
        response = await client.post(
            f"{BASE}/login",
            json={"login_id": login_id, "password": PASSWORD, "remember": remember},
        )
        assert response.status_code == 200
        return str(response.json()["access_token"])

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestRotation(SessionTestCase):
    async def test_refresh_swaps_the_cookie(self) -> None:
        """쓸 때마다 새 리프레시 토큰을 준다."""
        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            before = client.cookies["refresh_token"]

            response = await client.post(f"{BASE}/refresh")

            assert response.status_code == 200
            assert "access_token" in response.json()
            assert client.cookies["refresh_token"] != before

    async def test_used_token_is_dead_immediately(self) -> None:
        """쓴 것은 즉시 폐기한다 — 같은 토큰으로 두 번 갱신할 수 없다."""
        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            stale = client.cookies["refresh_token"]
            await client.post(f"{BASE}/refresh")

            client.cookies.set("refresh_token", stale, path="/api/v1/auth")
            response = await client.post(f"{BASE}/refresh")

        assert response.status_code == 401

    async def test_remember_survives_rotation(self) -> None:
        """로그인 유지를 켜고 갱신했는데 세션 쿠키로 바뀌면, 브라우저를 닫는
        순간 「유지」가 거짓말이 된다."""
        from app.core import config

        await make_staff()

        async with self.client() as client:
            await self.sign_in(client, remember=True)
            response = await client.post(f"{BASE}/refresh")

        cookie = next(h for h in response.headers.get_list("set-cookie") if "refresh_token=" in h)
        assert f"Max-Age={config.REFRESH_TOKEN_EXPIRE_MINUTES * 60}" in cookie

    async def test_missing_cookie_is_401(self) -> None:
        async with self.client() as client:
            response = await client.post(f"{BASE}/refresh")

        assert response.status_code == 401
        assert response.json()["code"] == "token_expired"


class TestIdleTimeout(SessionTestCase):
    async def test_thirty_quiet_minutes_end_the_session(self) -> None:
        """접수대는 브라우저를 하루 종일 켜 둔다. 쿠키만으로는 탭만 닫고
        자리를 떠도 다음 사람이 그대로 들어간다."""
        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            self.redis.go_idle()

            response = await client.post(f"{BASE}/refresh")

        assert response.status_code == 401
        assert response.json()["code"] == "token_expired"

    async def test_idle_does_not_look_like_theft(self) -> None:
        """유휴로 끊긴 것은 그 토큰만 폐기한다.

        도난으로 오해해 전 세션을 끊으면, 점심 먹고 온 사람 때문에 다른
        자리까지 로그아웃된다.
        """
        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            self.redis.go_idle()
            response = await client.post(f"{BASE}/refresh")

        assert "revoked_sessions" not in response.json()

    async def test_activity_pushes_the_window_back(self) -> None:
        """갱신할 때마다 유휴 시계가 30분으로 되감긴다."""
        from app.services.session_store import IDLE_SECONDS

        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            await client.post(f"{BASE}/refresh")

        alive = self.redis.idle_keys()
        assert len(alive) == 1
        assert self.redis.ttls[alive[0]] == IDLE_SECONDS


class TestStolenToken(SessionTestCase):
    async def test_reuse_kills_every_session(self) -> None:
        """이미 폐기된 토큰이 다시 오면 **훔친 것이 쓰였다는 뜻**이다.

        원래 쓰던 사람의 새 토큰까지 함께 끊어야 도둑만 남는 일이 없다.
        """
        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            stolen = client.cookies["refresh_token"]
            await client.post(f"{BASE}/refresh")  # 진짜 사용자가 한 번 갱신
            fresh = client.cookies["refresh_token"]

            # 도둑이 훔쳐 둔 옛 토큰을 쓴다
            client.cookies.set("refresh_token", stolen, path="/api/v1/auth")
            caught = await client.post(f"{BASE}/refresh")

            # 진짜 사용자의 토큰도 이제 못 쓴다
            client.cookies.set("refresh_token", fresh, path="/api/v1/auth")
            victim = await client.post(f"{BASE}/refresh")

        assert caught.status_code == 401
        assert caught.json()["revoked_sessions"] >= 1
        assert victim.status_code == 401

    async def test_two_devices_do_not_look_like_theft(self) -> None:
        """한 사람이 두 자리에서 쓰는 것은 도난이 아니다.

        접수대와 원장실에서 같은 계정을 쓰는 일이 실제로 있다. 한쪽이 갱신할
        때마다 다른 쪽이 끊기면 못 쓴다.
        """
        await make_staff()

        async with self.client() as desk, self.client() as room:
            await self.sign_in(desk)
            await self.sign_in(room)

            first = await desk.post(f"{BASE}/refresh")
            second = await room.post(f"{BASE}/refresh")

        assert first.status_code == 200
        assert second.status_code == 200


class TestLogout(SessionTestCase):
    async def test_logout_clears_cookie_and_kills_refresh(self) -> None:
        await make_staff()

        async with self.client() as client:
            token = await self.sign_in(client)

            response = await client.post(f"{BASE}/logout", headers={"Authorization": f"Bearer {token}"})
            after = await client.post(f"{BASE}/refresh")

        assert response.status_code == 204
        assert after.status_code == 401

    async def test_access_token_stops_working_after_logout(self) -> None:
        """「로그아웃 후 보호 API 와 화면에 접근할 수 없음」이 인수조건이다.

        액세스 토큰은 서명만으로 도는 것이 원칙이라, 이것만은 매 요청 확인한다.
        """
        await make_staff()

        async with self.client() as client:
            token = await self.sign_in(client)
            headers = {"Authorization": f"Bearer {token}"}
            await client.post(f"{BASE}/logout", headers=headers)

            again = await client.post(f"{BASE}/logout", headers=headers)

        assert again.status_code == 401
        assert again.json()["code"] == "token_expired"

    async def test_logout_needs_a_token(self) -> None:
        async with self.client() as client:
            response = await client.post(f"{BASE}/logout")

        assert response.status_code == 401
        assert response.json()["code"] == "token_expired"


class TestStaffWhoLeft(SessionTestCase):
    async def test_refresh_stops_for_someone_who_left(self) -> None:
        """로그인한 뒤에 그만둔 사람. 세션이 살아 있어도 더는 못 들어온다."""
        staff = await make_staff()

        async with self.client() as client:
            await self.sign_in(client)

            staff.status = StaffStatus.LEFT
            await staff.save()

            response = await client.post(f"{BASE}/refresh")

        assert response.status_code == 401


class TestPasswordGate(SessionTestCase):
    async def test_first_login_can_still_log_out(self) -> None:
        """비밀번호를 바꿔야 하는 사람도 로그아웃은 할 수 있어야 한다.

        `/auth/me` · `PATCH /auth/password` · `POST /auth/logout` 셋까지 막으면
        비밀번호를 바꿀 방법이 없어 계정이 영영 잠긴다.
        """
        await make_staff(must_change_password=True)

        async with self.client() as client:
            token = await self.sign_in(client)
            response = await client.post(f"{BASE}/logout", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 204


class TestTokenKindIsChecked(SessionTestCase):
    """리프레시 토큰을 액세스 토큰처럼 쓸 수 없다.

    서명은 같은 열쇠로 하므로 **종류를 안 보면 그대로 통과한다.** 그러면
    리프레시(14일)가 액세스처럼 쓰이는데, 그 jti 는 `revoked_access:` 에
    들어간 적이 없어 로그아웃도 유휴 30분도 걸리지 않는다.
    """

    async def test_refresh_token_is_not_accepted_as_bearer(self) -> None:
        await make_staff()

        async with self.client() as client:
            await self.sign_in(client)
            refresh = client.cookies["refresh_token"]

            response = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {refresh}"})

        assert response.status_code == 401

    async def test_access_token_is_not_accepted_as_refresh(self) -> None:
        """반대쪽도 막는다 — 액세스를 쿠키에 넣어 갱신을 시도하는 경우."""
        await make_staff()

        async with self.client() as client:
            access = await self.sign_in(client)
            client.cookies.set("refresh_token", access, path=REFRESH_PATH)

            response = await client.post(f"{BASE}/refresh")

        assert response.status_code == 401


class TestRevokeAllKillsAccessToo(SessionTestCase):
    """세션을 전부 끊으면 **이미 발급된 액세스 토큰도** 죽어야 한다.

    `sessions:{staff_id}` 에는 리프레시 jti 만 들어 있어서, 예전에는 이 함수가
    리프레시만 죽였다. 그러면 도난이 감지되거나 비밀번호를 바꿔도 액세스
    토큰이 최대 60분 더 살아서, 훔친 쪽이 그동안 계속 들어온다.
    """

    async def test_stolen_refresh_kills_the_access_token_in_hand(self) -> None:
        staff = await make_staff()

        async with self.client() as client:
            access = await self.sign_in(client)
            stolen = client.cookies["refresh_token"]
            await client.post(f"{BASE}/refresh")  # 정상 갱신 — 훔친 것은 이제 폐기됨

            # 도난 감지: 폐기된 토큰이 다시 왔다 → 이 계정 세션 전부 폐기
            client.cookies.set("refresh_token", stolen, path=REFRESH_PATH)
            theft = await client.post(f"{BASE}/refresh")

            # 그 사이 손에 들고 있던 액세스 토큰도 더는 못 쓴다
            after = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {access}"})

        assert theft.status_code == 401
        assert after.status_code == 401, "도난 감지 뒤에도 액세스 토큰이 살아 있다"
        assert staff.staff_id

    async def test_password_change_kills_the_access_token_in_hand(self) -> None:
        await make_staff()

        async with self.client() as client:
            access = await self.sign_in(client)
            changed = await client.patch(
                f"{BASE}/password",
                json={"new_password": "NewPassword123!", "current_password": PASSWORD},
                headers={"Authorization": f"Bearer {access}"},
            )
            after = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {access}"})

        assert changed.status_code == 204
        assert after.status_code == 401, "비밀번호를 바꿨는데 옛 액세스 토큰이 살아 있다"
