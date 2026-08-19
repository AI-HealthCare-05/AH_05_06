from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.core.validators import validate_birthday, validate_password, validate_phone_number
from app.models.users import Gender


class SignUpRequest(BaseModel):
    email: Annotated[
        EmailStr,
        Field(None, max_length=40),
    ]
    password: Annotated[str, Field(min_length=8), AfterValidator(validate_password)]
    name: Annotated[str, Field(max_length=20)]
    gender: Gender
    birth_date: Annotated[date, AfterValidator(validate_birthday)]
    phone_number: Annotated[str, AfterValidator(validate_phone_number)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]


class LoginResponse(BaseModel):
    access_token: str


class TokenRefreshResponse(LoginResponse): ...


class StaffLoginRequest(BaseModel):
    """계약 4절 — `{ "login_id": "staff01", "password": "…", "remember": false }`

    `login_id` 규칙은 `^[a-z0-9]{4,}$` 이지만 **로그인에서는 검사하지 않는다.**
    형식으로 걸러 422 를 주면, 규칙에 안 맞는 문자열이 「없는 아이디」와 다른
    답을 받아 계정 존재 여부를 흘린다. 형식 검사는 계정을 만들 때 한다.
    """

    login_id: Annotated[str, Field(min_length=1, max_length=50)]
    password: Annotated[str, Field(min_length=1, max_length=128)]
    remember: bool = False


class StaffLoginResponse(BaseModel):
    """본문에는 액세스 토큰만 온다. 리프레시는 HttpOnly 쿠키로만 내려간다."""

    access_token: str
    must_change_password: bool
