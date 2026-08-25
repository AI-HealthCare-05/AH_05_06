from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.core.validators import (
    validate_birthday,
    validate_password,
    validate_phone_number,
    validate_staff_password,
)
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
    """계약 4절 — `{ "login_id": "staff01", "password": "…" }`

    `login_id` 규칙은 `^[a-z0-9]{4,}$` 이지만 **로그인에서는 검사하지 않는다.**
    형식으로 걸러 422 를 주면, 규칙에 안 맞는 문자열이 「없는 아이디」와 다른
    답을 받아 계정 존재 여부를 흘린다. 형식 검사는 계정을 만들 때 한다.
    """

    login_id: Annotated[str, Field(min_length=1, max_length=50)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class StaffLoginResponse(BaseModel):
    """본문에는 액세스 토큰만 온다. 리프레시는 HttpOnly 쿠키로만 내려간다."""

    access_token: str
    must_change_password: bool


class StaffMeResponse(BaseModel):
    """세션 복원과 화면 분기의 근거. 새로고침할 때마다 부른다(계약 4절).

    `roles` 로 FE 가 초기 화면(`S1`/`D1`/`A1`)과 어드민 메뉴 노출을 정한다.
    **노출 여부는 편의일 뿐이고 실제 차단은 서버가 한다**(KEY-9).
    """

    id: int
    name: str
    login_id: str
    roles: list[str]
    must_change_password: bool
    clinic_name: str


class PasswordChangeRequest(BaseModel):
    """두 경우가 요청 조건이 다르다(계약 4절).

    최초 로그인 — `{ new_password }` 만 온다. 방금 그 비밀번호로 로그인했는데
                  한 화면에서 같은 값을 두 번 넣게 하면 거기서부터 막힌다.
    일반 변경   — `{ current_password, new_password }`. 자리를 비운 사이 남이
                  바꾸는 것을 막는다.

    **어느 쪽인지는 서버가 `must_change_password` 로 정한다.** 요청이 정하게
    두면 최초 로그인이 아닌 사람도 `current_password` 를 빼고 보내면 통과한다.
    """

    current_password: str | None = None
    new_password: Annotated[str, AfterValidator(validate_staff_password)]
