"""직원 로그인이 계약대로 답하는지 본다 — KEY-73.

계약은 `docs/api/hospital.md` 3·4·5절이다. 여기서 지키려는 것은 대부분
**무엇을 알려주지 않는가**라, 눈으로 확인하기 어렵다. 그래서 검사로 못 박는다.
"""

from typing import Any, cast

from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.staffs import Hospital, Staff, StaffStatus
from app.services.login_attempts import LOCK_SECONDS, MAX_FAILURES
from app.tests.fakes import FakeRedis, InterleavingRedis

PASSWORD = "Password123!"
LOGIN_URL = "/api/v1/auth/login"


async def make_staff(
    login_id: str = "staff01",
    *,
    status: StaffStatus = StaffStatus.ACTIVE,
    must_change_password: bool = False,
) -> Staff:
    hospital, _ = await Hospital.get_or_create(name="여성의원")
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password(PASSWORD),
        name="한소영",
        roles=["staff"],
        status=status,
        must_change_password=must_change_password,
    )


class StaffLoginTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def post(self, **body: Any) -> Any:
        payload = {"login_id": "staff01", "password": PASSWORD, **body}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(LOGIN_URL, json=payload)


class TestLoginSucceeds(StaffLoginTestCase):
    async def test_body_carries_access_token_only(self) -> None:
        """리프레시 토큰은 본문에 담지 않는다 — HttpOnly 쿠키로만 내려간다."""
        await make_staff()

        response = await self.post()

        assert response.status_code == 200
        assert set(response.json()) == {"access_token", "must_change_password"}
        assert "refresh_token" not in response.text

    async def test_refresh_cookie_is_http_only_and_scoped(self) -> None:
        await make_staff()

        response = await self.post()

        cookie = next(h for h in response.headers.get_list("set-cookie") if "refresh_token=" in h)
        assert "HttpOnly" in cookie
        assert "Path=/api/v1/auth" in cookie
        assert "SameSite=lax" in cookie

    async def test_the_refresh_cookie_is_always_a_session_cookie(self) -> None:
        """**접수 PC 는 공용이다** — 브라우저를 닫으면 인증이 사라져야 한다 (KEY-179).

        예전에는 「이 컴퓨터에서 로그인 유지」를 켜면 쿠키에 `Max-Age` 가 붙어
        14 일을 남았다. 자리를 뜬 뒤 다음 사람이 그 인증을 그대로 물려받는다.
        선택지 자체를 없앴으므로 **어떤 요청에도 수명이 붙지 않는다.**

        영속 `Expires` 도 함께 본다 — `Max-Age` 만 막으면 그쪽으로 새어 나간다.
        """
        await make_staff()

        response = await self.post()

        cookie = next(h for h in response.headers.get_list("set-cookie") if "refresh_token=" in h)
        assert "Max-Age" not in cookie, f"쿠키에 수명이 붙었다: {cookie}"
        assert "Expires" not in cookie, f"쿠키에 만료 날짜가 붙었다: {cookie}"

    async def test_asking_to_be_remembered_changes_nothing(self) -> None:
        """**계약에서 사라진 것을 보내도 수명이 안 붙는다.**

        옛 화면이 캐시에 남아 `remember: true` 를 보낼 수 있고, 손으로 부르는
        사람도 있다. 「필드를 지웠다」로 끝내면 그 요청이 조용히 옛 동작을
        되살릴 자리가 남는다.
        """
        await make_staff()

        response = await self.post(remember=True)

        assert response.status_code == 200, response.text
        cookie = next(h for h in response.headers.get_list("set-cookie") if "refresh_token=" in h)
        assert "Max-Age" not in cookie, f"지운 필드가 되살아났다: {cookie}"

    async def test_first_login_is_reported(self) -> None:
        """화면(L-3)이 비밀번호 변경으로 보낼 근거다."""
        await make_staff(must_change_password=True)

        response = await self.post()

        assert response.json()["must_change_password"] is True

    async def test_success_clears_earlier_failures(self) -> None:
        """어제 오타 두 번이 오늘까지 따라오지 않는다."""
        await make_staff()
        await self.post(password="wrong")
        await self.post(password="wrong")

        assert await self.redis.get("login_fail:staff01") == "2"

        await self.post()

        assert await self.redis.get("login_fail:staff01") is None


class TestLoginHidesWhoExists(StaffLoginTestCase):
    """세 가지 실패가 **똑같이** 보여야 한다."""

    async def _codes(self) -> list[Any]:
        await make_staff("staff01")
        await make_staff("left01", status=StaffStatus.LEFT)

        missing = await self.post(login_id="nobody01")
        wrong = await self.post(login_id="staff01", password="wrong")
        # 퇴사자는 **맞는 비밀번호**로 시도한다 — 그래도 같은 답이어야 한다
        left = await self.post(login_id="left01")
        return [missing, wrong, left]

    async def test_same_status_and_code(self) -> None:
        for response in await self._codes():
            assert response.status_code == 401
            assert response.json()["code"] == "invalid_credentials"

    async def test_same_message(self) -> None:
        messages = {response.json()["message"] for response in await self._codes()}
        assert len(messages) == 1

    async def test_failures_count_even_for_unknown_ids(self) -> None:
        """없는 아이디에서 횟수가 안 오르면, **안 오른다는 사실이 답이 된다.**"""
        response = await self.post(login_id="nobody01", password="whatever")

        assert response.json()["fail_count"] == 1
        assert await self.redis.get("login_fail:nobody01") == "1"

    async def test_left_staff_failure_also_counts(self) -> None:
        """퇴사자만 카운터가 안 움직이면 그 차이로 퇴사 여부가 드러난다."""
        await make_staff("left01", status=StaffStatus.LEFT)

        response = await self.post(login_id="left01")  # 비밀번호는 맞다

        assert response.json()["fail_count"] == 1


class TestLockout(StaffLoginTestCase):
    async def test_locks_after_five_failures(self) -> None:
        await make_staff()

        for expected in range(1, MAX_FAILURES):
            response = await self.post(password="wrong")
            assert response.status_code == 401
            assert response.json()["fail_count"] == expected

        locked = await self.post(password="wrong")

        assert locked.status_code == 429
        assert locked.json()["code"] == "ACCOUNT_LOCKED"

    async def test_lock_answer_carries_retry_after(self) -> None:
        """표준 헤더와 본문 둘 다 준다 — 프록시도 읽고 화면도 「10분」을 계산한다."""
        await make_staff()
        for _ in range(MAX_FAILURES):
            await self.post(password="wrong")

        locked = await self.post(password="wrong")

        assert locked.headers["Retry-After"] == str(LOCK_SECONDS)
        assert locked.json()["retry_after_seconds"] == LOCK_SECONDS

    async def test_correct_password_does_not_open_a_locked_id(self) -> None:
        """맞았을 때만 통과시키면 잠금이 「비밀번호 맞추기」의 속도만 늦춘다."""
        await make_staff()
        for _ in range(MAX_FAILURES):
            await self.post(password="wrong")

        response = await self.post()  # 진짜 비밀번호

        assert response.status_code == 429

    async def test_unknown_id_locks_the_same_way(self) -> None:
        for _ in range(MAX_FAILURES):
            await self.post(login_id="nobody01", password="wrong")

        response = await self.post(login_id="nobody01", password="wrong")

        assert response.status_code == 429
        assert response.json()["code"] == "ACCOUNT_LOCKED"

    async def test_lock_window_is_set_once(self) -> None:
        """실패할 때마다 TTL 을 다시 걸면 계속 두드리는 동안 영영 안 풀린다.

        TTL 값만 보면 다시 걸어도 600 그대로라 차이가 안 보인다 —
        **몇 번 걸었는지**를 봐야 잡힌다.
        """
        await make_staff()

        await self.post(password="wrong")
        await self.post(password="wrong")
        await self.post(password="wrong")

        assert self.redis.values["login_fail:staff01"] == 3
        assert self.redis.expire_calls["login_fail:staff01"] == 1
        assert self.redis.ttls["login_fail:staff01"] == LOCK_SECONDS


class TestRequestShape(StaffLoginTestCase):
    async def test_missing_fields_are_422(self) -> None:
        """예전 계약(email)으로 부르면 통과하지 않는다 — 갈아탄 것이 검사에 남는다."""
        bodies = [{"email": "a@b.c", "password": PASSWORD}, {"login_id": "staff01"}, {}]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for body in bodies:
                response = await client.post(LOGIN_URL, json=body)
                assert response.status_code == 422, body

    async def test_short_login_id_is_not_rejected_by_format(self) -> None:
        """아이디 규칙(`^[a-z0-9]{4,}$`)으로 422 를 주면 안 된다.

        규칙에 안 맞는 문자열만 다른 답을 받으면, 그 차이가 계정 존재 여부를
        가려내는 도구가 된다. 형식은 계정을 만들 때 본다.
        """
        response = await self.post(login_id="ab")

        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"


class TestLockoutFoldsCase(StaffLoginTestCase):
    """대소문자를 바꿔 가며 두드려도 잠금이 풀리지 않는다.

    DB 는 `utf8mb4_unicode_ci` 라 `Staff01` 과 `staff01` 이 **같은 계정**을
    찾는다. 그런데 실패 횟수를 입력 문자열 그대로 세면 대소문자마다 별개
    카운터가 생겨서, `staff01` · `Staff01` · `STAFF01` … 로 돌려 가며
    사실상 무제한으로 시도할 수 있다 — 5회 잠금이 무력해진다.
    """

    async def test_mixed_case_shares_one_counter(self) -> None:
        await make_staff()

        for spelling in ("staff01", "Staff01", "STAFF01", "sTaFf01", "staFF01"):
            await self.post(login_id=spelling, password="wrong")

        # 다섯 번 틀렸으니 잠겨 있어야 한다 — 철자를 어떻게 바꿔 왔든.
        response = await self.post()

        assert response.status_code == 429, "대소문자를 바꾸면 잠금을 우회할 수 있다"

    async def test_the_lock_applies_to_the_other_spellings_too(self) -> None:
        await make_staff()

        for _ in range(MAX_FAILURES):
            await self.post(password="wrong")

        response = await self.post(login_id="STAFF01")

        assert response.status_code == 429


class TestLockoutCountsBeforeChecking(StaffLoginTestCase):
    """시도를 **비밀번호를 보기 전에** 센다.

    예전에는 `is_locked()` 로 보고 나서 실패했을 때만 셌다. 보는 것과 세는 것이
    갈라져 있으면 동시에 온 요청들이 전부 같은 숫자를 보고 통과해, 한 번에
    여러 개를 보내는 것만으로 제한을 넘겨 비밀번호를 더 시험할 수 있다.

    API 로는 이 경합을 여기서 재현할 수 없다 — 비밀번호 해시 검증이 동기라
    이벤트 루프를 붙잡고 있어 요청들이 사실상 줄을 선다. 그래서 **세는 자리
    자체**를 본다. `INCR` 은 원자적이라 동시에 불러도 번호가 겹치지 않는다.
    """

    async def test_concurrent_attempts_get_distinct_numbers(self) -> None:
        import asyncio

        from app.services.login_attempts import LoginAttempts

        attempts = LoginAttempts(cast("Redis", InterleavingRedis()))
        numbers = await asyncio.gather(*(attempts.begin("staff01") for _ in range(12)))

        assert sorted(numbers) == list(range(1, 13)), f"번호가 겹친다: {sorted(numbers)}"

    async def test_a_successful_login_does_not_leave_a_count(self) -> None:
        """맞혀서 들어가면 세어 둔 것을 지운다 — 어제 오타가 오늘 따라오지 않게."""
        await make_staff()

        await self.post(password="wrong")
        await self.post()

        assert await self.redis.get("login_fail:staff01") is None

    async def test_the_limit_still_holds_under_a_burst(self) -> None:
        """한꺼번에 밀어 넣어도 비밀번호를 본 횟수가 제한을 넘지 않는다."""
        import asyncio

        await make_staff()

        results = await asyncio.gather(*(self.post(password="wrong") for _ in range(12)))
        codes = [r.status_code for r in results]

        assert codes.count(401) <= MAX_FAILURES, f"{codes.count(401)}회까지 시험할 수 있다"
