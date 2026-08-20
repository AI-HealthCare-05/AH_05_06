from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core.utils.security import hash_password
from app.main import app
from app.models.users import Gender, User
from app.services.jwt import JwtService


async def make_user(email: str, name: str, gender: Gender, birthday: str, phone: str) -> User:
    """검사가 쓸 사용자를 **모델로 직접** 만든다.

    예전에는 `POST /auth/signup` 을 불렀는데, 그 경로는 지웠다 — email 로
    `User` 를 만들지만 로그인은 `login_id` 로 `Staff` 를 찾아서, 그렇게 만든
    계정은 영원히 로그인할 수 없었다(KEY-73 리뷰). 이 검사가 보려는 것은
    `/users/me` 이지 가입이 아니므로 만드는 방법만 바꾼다.
    """
    return await User.create(
        email=email,
        hashed_password=hash_password("Password123!"),
        name=name,
        gender=gender,
        birthday=birthday,
        phone_number=phone,
    )


async def token_for(email: str) -> str:
    """로그인을 거치지 않고 토큰을 만든다.

    이 검사가 보려는 것은 `/users/me` 이지 로그인이 아니다. 로그인은 계약이
    바뀌면(KEY-73: email → login_id) 같이 바뀌는데, 그때마다 상관없는 검사가
    함께 깨지면 무엇이 진짜 고장인지 안 보인다.
    """
    user = await User.get(email=email)
    return str(JwtService().issue_jwt_pair(user)["access_token"])


class TestUserMeApis(TestCase):
    async def test_get_user_me_success(self):
        email = "me@example.com"
        await make_user(email, "내정보테스터", Gender.FEMALE, "1992-02-02", "01055556666")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {await token_for(email)}"}
            response = await client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["email"] == email
        assert response.json()["name"] == "내정보테스터"

    async def test_update_user_me_success(self):
        email = "update_me@example.com"
        await make_user(email, "수정전", Gender.MALE, "1990-10-10", "01077778888")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {await token_for(email)}"}
            response = await client.patch("/api/v1/users/me", json={"name": "수정후"}, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "수정후"

    async def test_get_user_me_unauthorized(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
