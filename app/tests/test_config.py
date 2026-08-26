import pytest
from pydantic import ValidationError

from app.core.config import Config, Env


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
        OCR_FIXTURE_FALLBACK=False,
    )

    assert config.OCR_FIXTURE_FALLBACK is False
