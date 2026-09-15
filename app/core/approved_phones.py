"""OTP와 예약 문자에 공통으로 적용하는 Pilot 승인 수신번호 목록."""

from app.core import config
from app.core.utils.common import normalize_phone_number


def approved_test_phones() -> frozenset[str]:
    raw = config.OTP_APPROVED_TEST_PHONES.get_secret_value()
    return frozenset(normalize_phone_number(phone.strip()) for phone in raw.split(",") if phone.strip())
