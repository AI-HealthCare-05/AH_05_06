"""로그인·세션을 재는 검사가 서는 **공용 바닥** — KEY-173.

## 왜 모으나

`COOKIE_DOMAIN` 을 비웠다 되돌리는 똑같은 네 줄이 네 파일에 복제돼 있었다.
그리고 **다섯 번째가 그걸 빠뜨린 채 들어왔다** — `#119`(KEY-92)의
`test_patient_session.py` 다. `.env` 에 `COOKIE_DOMAIN` 이 있는 로컬에서
쿠키가 통째로 버려져 두 검사가 「쿠키가 없다」로 깨졌는데, CI 에는 `.env` 가
없어 초록불이었다.

복제된 규약은 이렇게 샌다 — 아는 사람은 적고 모르는 사람은 안 적는다.
바닥을 하나 두면 **상속만 해도 따라온다.**

## 무엇을 담나

    COOKIE_DOMAIN 을 비웠다 되돌리기   `.env` 가 검사를 좌우하지 않게
    FakeRedis 를 끼우기                세션 저장소를 진짜 Redis 에 안 기대게

`login_headers()` 는 **부르는 쪽 클라이언트를 받는다.** e2e 는 한 클라이언트로
여정을 이어가며 쿠키를 물려받아야 해서, 안에서 새로 만들면 안 된다.
"""

from typing import Any

from httpx import AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.staffs import Hospital, Staff
from app.tests.fakes import FakeRedis

#: 합성 비밀번호. 실제 계정 비밀번호가 아니다.
PASSWORD = "Synthetic-password-1!"

LOGIN_URL = "/api/v1/auth/login"


async def make_staff_account(
    hospital: Hospital,
    login_id: str,
    roles: list[str],
    *,
    name: str = "합성직원",
    **extra: Any,
) -> Staff:
    """그 의원의 직원 하나. 비밀번호는 실제 해시 경로를 탄다."""
    fields: dict[str, Any] = {
        "hospital": hospital,
        "login_id": login_id,
        "password_hash": hash_password(PASSWORD),
        "name": name,
        "roles": roles,
        "must_change_password": False,
    }
    fields.update(extra)
    return await Staff.create(**fields)


async def login_headers(client: AsyncClient, login_id: str, password: str = PASSWORD) -> dict[str, str]:
    """**라우트를 통해** 액세스 토큰을 얻는다. 손으로 만들지 않는다.

    리프레시 토큰이 본문에 실리지 않는 것도 함께 본다 — 계약이다
    (`docs/api/hospital.md` 2절). 로그인을 타는 모든 검사가 이 한 줄을
    공짜로 얻는다.
    """
    response = await client.post(LOGIN_URL, json={"login_id": login_id, "password": password})
    assert response.status_code == 200, f"{login_id} 로그인이 {response.status_code} 다 — 검사가 설 바닥이 없다"
    assert "refresh_token" not in response.text, "리프레시 토큰이 본문에 실렸다"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class AuthTestCase(TestCase):
    """로그인·세션 검사의 바닥.

    `setUp`/`tearDown` 을 더 할 일이 있으면 **`super()` 를 먼저 부른다.**
    """

    redis: FakeRedis

    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis
        # `.env` 에 `COOKIE_DOMAIN` 이 박혀 있으면 테스트 클라이언트의 호스트
        # (`test`)와 안 맞아 **쿠키가 통째로 버려진다.** 그러면 rotation·로그아웃
        # 검사가 전부 「쿠키가 없다」로 깨진다. 검사가 개발자 `.env` 에
        # 좌우되면 안 된다 — `config.py` 주석이 경고하는 그 상황이다.
        self._cookie_domain = config.COOKIE_DOMAIN
        config.COOKIE_DOMAIN = ""

    def tearDown(self) -> None:
        config.COOKIE_DOMAIN = self._cookie_domain
        app.dependency_overrides.clear()
        super().tearDown()
