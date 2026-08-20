from typing import Literal, overload

from fastapi import HTTPException

from app.core.jwt.exceptions import ExpiredTokenError, TokenError
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.models.users import User


class JwtService:
    access_token_class = AccessToken
    refresh_token_class = RefreshToken

    def create_access_token(self, user: User) -> AccessToken:
        return self.access_token_class.for_user(user)

    def create_refresh_token(self, user: User) -> RefreshToken:
        return self.refresh_token_class.for_user(user)

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["access"],
    ) -> AccessToken: ...

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["refresh"],
    ) -> RefreshToken: ...

    def verify_jwt(self, token: str, token_type: Literal["access", "refresh"]) -> AccessToken | RefreshToken:
        token_class: type[AccessToken | RefreshToken]
        if token_type == "access":
            token_class = self.access_token_class
        else:
            token_class = self.refresh_token_class

        try:
            verified = token_class(token=token)
            return verified
        except ExpiredTokenError as err:
            raise HTTPException(status_code=401, detail=f"{token_type} token has expired.") from err
        except TokenError as err:
            raise HTTPException(status_code=400, detail="Provided invalid token.") from err

    # refresh_jwt() 는 지웠다. 서명만 보고 액세스 토큰을 찍어 주는 지름길이라,
    # 어디서 다시 부르면 세션 확인(로그아웃 · 재사용 감지 · 유휴 · 퇴사자)을
    # 통째로 건너뛴다. 갱신은 `StaffSessionService.rotate()` 하나로 간다.

    def issue_jwt_pair(self, user: User) -> dict[str, AccessToken | RefreshToken]:
        rt = self.create_refresh_token(user)
        at = rt.access_token
        return {"access_token": at, "refresh_token": rt}
