"""토큰 수명이 설정값과 같은 단위로 읽히는가 — DB도 서버도 필요 없다.

KEY-10. 설정 이름은 `..._MINUTES`인데 코드가 `timedelta(days=...)`로 읽어
리프레시 토큰이 14일 대신 20160일(약 55년)이던 것을 고치면서 붙였다.

같은 실수가 눈에 안 띄는 이유는 **둘 다 그럴듯한 숫자가 나오기 때문**이다.
20160은 분으로 읽으면 14일, 일로 읽으면 55년인데 어느 쪽도 예외를 내지 않는다.
그래서 값을 눈으로 보는 대신 설정과 맞춰 본다.
"""

from datetime import timedelta

from app.core import config
from app.core.jwt.tokens import AccessToken, RefreshToken

#: 리프레시 토큰이 이보다 길면 무언가 잘못된 것이다.
#: 액세스 토큰을 짧게 잡아도, 그것을 새로 찍어내는 열쇠가 길면 의미가 없다.
MAX_SANE_REFRESH = timedelta(days=90)


class TestLifetimeMatchesConfig:
    def test_access_token_reads_minutes(self) -> None:
        assert AccessToken.lifetime == timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)

    def test_refresh_token_reads_minutes(self) -> None:
        """이름이 `_MINUTES`면 `minutes=`로 읽어야 한다.

        `days=`로 읽으면 20160이 14일이 아니라 20160일이 된다.
        """
        assert RefreshToken.lifetime == timedelta(minutes=config.REFRESH_TOKEN_EXPIRE_MINUTES)


class TestLifetimeIsSane:
    def test_refresh_outlives_access(self) -> None:
        """리프레시가 액세스보다 짧으면 재발급이 무의미하다."""
        assert RefreshToken.lifetime > AccessToken.lifetime

    def test_refresh_is_not_absurdly_long(self) -> None:
        """설정값을 바꾸다 단위를 헷갈려도 여기서 걸린다.

        토큰이 새면 비밀번호를 바꿔도 끊을 방법이 아직 없다(로그아웃 미구현).
        그동안은 수명이 유일한 방어선이다.
        """
        assert RefreshToken.lifetime <= MAX_SANE_REFRESH, (
            f"리프레시 토큰이 {RefreshToken.lifetime.days}일이다 — 단위를 잘못 읽고 있지 않은지 보라"
        )

    def test_access_is_short(self) -> None:
        assert AccessToken.lifetime <= timedelta(hours=24)
