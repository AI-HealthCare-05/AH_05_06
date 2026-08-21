from calendar import timegm
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Self
from uuid import uuid4

from app.core import config
from app.core.jwt.exceptions import ExpiredTokenError, TokenBackendError, TokenBackendExpiredError, TokenError
from app.core.jwt.state import token_backend
from app.models.users import User

if TYPE_CHECKING:
    from app.core.jwt.backends import TokenBackend


class Token:
    token_type: str | None = None
    lifetime: timedelta | None = None
    _token_backend: "TokenBackend" = token_backend

    def __init__(self, token: str | None = None, verify: bool = True) -> None:
        if not self.token_type:
            raise TokenError("token_type must be set")
        if not self.lifetime:
            raise TokenError("lifetime must be set")

        self.token = token
        self.current_time = datetime.now(tz=config.TIMEZONE)
        self.payload: dict[str, Any] = {}

        if token is not None:
            try:
                self.payload = token_backend.decode(token, verify=verify)
            except TokenBackendExpiredError as err:
                raise ExpiredTokenError("Token is expired") from err
            except TokenBackendError as err:
                raise TokenError("Token is invalid") from err

            # 서명이 맞아도 **종류가 다르면 받지 않는다.**
            #
            # 이 확인이 없으면 리프레시 토큰을 그대로 `Authorization: Bearer` 로
            # 보냈을 때 액세스 토큰으로 통과한다. 리프레시는 수명이 14일이고
            # `revoked_access:` 목록에 들어간 적이 없어서, 유휴 30분도 로그아웃도
            # 걸리지 않는 채로 그 기간 내내 보호 API 를 열 수 있다.
            if self.payload.get("type") != self.token_type:
                raise TokenError(f"Expected a {self.token_type} token")
        else:
            self.payload = {"type": self.token_type}
            self.set_exp(from_time=self.current_time, lifetime=self.lifetime)
            self.set_iat()
            self.set_jti()

    def __repr__(self) -> str:
        return repr(self.payload)

    def __getitem__(self, key: str):
        return self.payload[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.payload[key] = value

    def __delitem__(self, key: str) -> None:
        del self.payload[key]

    def __contains__(self, key: str) -> Any:
        return key in self.payload

    def __str__(self) -> str:
        """
        Signs and returns a token as a base64 encoded string.
        """
        return self._token_backend.encode(self.payload)

    def set_exp(self, from_time: datetime | None = None, lifetime: timedelta | None = None) -> None:
        if from_time is None:
            from_time = self.current_time

        if lifetime is None:
            lifetime = self.lifetime

        assert lifetime is not None

        dt = from_time + lifetime
        # utctimetuple() 로 UTC 로 옮긴 뒤 epoch 으로 만든다.
        # timetuple() 을 쓰면 KST 벽시계를 UTC 로 읽어 **9시간이 더 붙는다** —
        # 60분짜리 액세스 토큰이 실제로는 600분을 살았다. 설정과 계약
        # (docs/api/hospital.md 4절)이 말하는 수명과 어긋난다.
        self.payload["exp"] = timegm(dt.utctimetuple())

    def set_iat(self, from_time: datetime | None = None) -> None:
        """발급 시각. 「이 사람의 토큰을 전부 끊는다」의 기준이 된다.

        액세스 토큰은 jti 를 하나씩 모아 두기엔 수가 많다. 대신 계정마다
        「언제 이전에 발급된 것은 무효」라는 한 줄만 두고 이 값과 견준다
        (`SessionStore.revoke_all`).
        """
        self.payload["iat"] = timegm((from_time or self.current_time).utctimetuple())

    def set_jti(self) -> None:
        self.payload["jti"] = uuid4().hex

    @classmethod
    def for_user(cls, user: User) -> Self:
        token = cls()
        token["user_id"] = user.id
        return token


class AccessToken(Token):
    token_type = "access"
    lifetime = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)


class RefreshToken(Token):
    token_type = "refresh"
    lifetime = timedelta(minutes=config.REFRESH_TOKEN_EXPIRE_MINUTES)
    # iat 를 물려주면 새 액세스 토큰이 리프레시가 발급된 시각을 달고 나온다.
    # 그러면 rotation 으로 갓 받은 토큰이 「폐기 시점 이전」으로 판정될 수 있다.
    no_copy_claims = ("type", "exp", "jti", "iat")

    @property
    def access_token(self) -> AccessToken:
        access = AccessToken()
        access.set_exp(from_time=self.current_time)
        access.set_iat(from_time=self.current_time)

        no_copy = self.no_copy_claims
        for claim, value in self.payload.items():
            if claim in no_copy:
                continue
            access[claim] = value

        return access
