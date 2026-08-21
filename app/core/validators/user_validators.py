import re
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from app.core import config


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")

    # 대문자를 포함하고 있는지
    if not re.search(r"[A-Z]", password):
        raise ValueError("비밀번호에는 대문자, 소문자, 특수문자, 숫자가 각 하나씩 포함되어야 합니다.")

    # 소문자를 포함하고 있는지
    if not re.search(r"[a-z]", password):
        raise ValueError("비밀번호에는 대문자, 소문자, 특수문자, 숫자가 각 하나씩 포함되어야 합니다.")

    # 숫자를 포함하고 있는지
    if not re.search(r"[0-9]", password):
        raise ValueError("비밀번호에는 대문자, 소문자, 특수문자, 숫자가 각 하나씩 포함되어야 합니다.")

    # 특수문자를 포함하고 있는지
    if not re.search(r"[^a-zA-Z0-9]", password):
        raise ValueError("비밀번호에는 대문자, 소문자, 특수문자, 숫자가 각 하나씩 포함되어야 합니다.")

    return password


def validate_phone_number(phone_number: str) -> str:
    patterns = [
        r"010-\d{4}-\d{4}",  # 010-1234-5678
        r"010\d{8}",  # 01012345678
        r"\+8210\d{8}",  # +821012345678
    ]

    if not any(re.fullmatch(p, phone_number) for p in patterns):
        raise ValueError("유효하지 않은 휴대폰 번호 형식입니다.")

    return phone_number


def validate_birthday(birthday: date | str) -> date:
    if isinstance(birthday, str):
        try:
            birthday = date.fromisoformat(birthday)
        except ValueError as e:
            raise ValueError("올바르지 않은 날짜 형식입니다. format: YYYY-MM-DD") from e

    is_over_14 = birthday < datetime.now(tz=config.TIMEZONE).date() - relativedelta(years=14)
    if not is_over_14:
        raise ValueError("서비스 약관에 따라 만14세 미만은 회원가입이 불가합니다.")

    return birthday


def validate_staff_password(password: str) -> str:
    """직원 비밀번호 — 계약(`docs/api/hospital.md` 2절)의 `L-3` 규칙.

    화면이 약속하는 것은 「영문 · 숫자 · 기호를 섞어 8자 이상」이다.
    위의 `validate_password` 는 **대문자를 따로 요구**해서, 화면 문구대로 만든
    비밀번호(`abcd1234!`)가 서버에서 거부된다. 화면과 서버가 다른 약속을 하면
    사용자는 무엇이 틀렸는지 알 수 없다.

    `validate_password` 는 회원가입(`/auth/signup`)이 쓰고 있고, 그 정리는
    계정 관리(A1-2) 몫이라 여기서 건드리지 않는다.
    """
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("영문 · 숫자 · 기호를 섞어 8자 이상으로 만들어 주세요.")
    if not re.search(r"[0-9]", password):
        raise ValueError("영문 · 숫자 · 기호를 섞어 8자 이상으로 만들어 주세요.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("영문 · 숫자 · 기호를 섞어 8자 이상으로 만들어 주세요.")
    return password
