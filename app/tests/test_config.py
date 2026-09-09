import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Config, Env, SmsProvider


def test_fixture_fallback_is_allowed_in_local() -> None:
    config = Config(
        ENV=Env.LOCAL,
        DB_PASSWORD="test-password",
        OCR_FIXTURE_FALLBACK=True,
    )

    assert config.OCR_FIXTURE_FALLBACK is True


@pytest.mark.parametrize("env", [Env.DEV, Env.PROD])
def test_fixture_fallback_is_rejected_outside_local(env: Env) -> None:
    with pytest.raises(
        ValidationError,
        match="OCR_FIXTURE_FALLBACK은 로컬 환경에서만 사용할 수 있습니다",
    ):
        Config(
            ENV=env,
            DB_PASSWORD="test-password",
            OCR_FIXTURE_FALLBACK=True,
        )


def test_disabled_fixture_fallback_is_allowed_outside_local() -> None:
    config = Config(
        ENV=Env.PROD,
        DB_PASSWORD="test-password",
        # 운영에서는 `SECRET_KEY` 가 있어야 뜬다(KEY-174). 여기서 재는 것은
        # fixture 스위치이지 비밀값이 아니므로 합성값을 준다.
        SECRET_KEY="synthetic-for-this-test",
        SMS_PROVIDER=SmsProvider.SOLAPI,
        SOLAPI_API_KEY=SecretStr("synthetic-api-key"),
        SOLAPI_API_SECRET=SecretStr("synthetic-api-secret"),
        SOLAPI_SENDER_NUMBER=SecretStr("0200000000"),
        OCR_FIXTURE_FALLBACK=False,
        # KEY-284 검증기가 SMS_PROVIDER=solapi면 이 목록을 요구한다 — 이
        # 테스트는 OCR_FIXTURE_FALLBACK을 재는 것이라 OTP와 무관하지만
        # Config 하나를 같이 쓰므로 채워야 부팅이 된다.
        OTP_APPROVED_TEST_PHONES=SecretStr("01000000000"),
    )

    assert config.OCR_FIXTURE_FALLBACK is False
