"""로그에 남으면 안 되는 것이 실제로 안 남는가 — KEY-11.

인수조건: 「대표 요청·오류 로그에서 토큰 원문과 전체 개인정보가 보이지 않음」

화면별로 무엇이 새어 나갈 수 있는지를 기준으로 짰다.
  L-1~L-3  계정 · 비밀번호 · JWT
  A1-1~A1-3  직원 계정 · 첫 비밀번호 · 재설정
  S1-2~S1-4  환자 기본정보
  P1-1~P1-5  링크 토큰 · OTP · 재발급 · 잠금
"""

import logging

import pytest

from app.core.logger import setup_logger
from app.core.masking import REDACTED, mask_phone, scrub

JWT_SAMPLE = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxMn0.s0m3S1gnatur3Va1u3Here"
LINK_TOKEN = "kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x"  # secrets.token_urlsafe(32) 모양


class TestSecretsDisappear:
    """가려야 할 것 — 남겨 봐야 쓸 데가 없고, 새면 그대로 열쇠다."""

    @pytest.mark.parametrize(
        "line",
        [
            'login failed for {"login_id": "staff01", "password": "Str0ng!Pass"}',
            "POST /auth/login password=Str0ng!Pass remember=false",
            "user row: hashed_password='$2b$12$abcdefghijklmnop'",
            'PATCH /auth/password {"current_password": "old1!", "new_password": "new1!"}',
        ],
        ids=["json", "querystring", "repr", "change"],
    )
    def test_passwords_never_survive(self, line: str) -> None:
        cleaned = scrub(line)
        for leaked in ("Str0ng!Pass", "$2b$12$abcdefghijklmnop", "old1!", "new1!"):
            assert leaked not in cleaned, f"비밀번호가 남았다: {cleaned}"
        assert REDACTED in cleaned

    def test_jwt_never_survives(self) -> None:
        cleaned = scrub(f"Authorization: Bearer {JWT_SAMPLE}")
        assert JWT_SAMPLE not in cleaned
        assert "eyJ" not in cleaned, "헤더 조각만 남아도 알고리즘이 드러난다"

    def test_patient_link_token_never_survives(self) -> None:
        """P1 링크 토큰은 그 자체로 환자 화면을 여는 열쇠다."""
        cleaned = scrub(f"issued link token={LINK_TOKEN} for visit 123")
        assert LINK_TOKEN not in cleaned

    @pytest.mark.parametrize(
        "line",
        ['otp="483920"', "otp=483920", '{"code": "483920"}', "OTP 483920 sent"],
        ids=["json", "kv", "code-key", "prose"],
    )
    def test_otp_never_survives_when_labelled(self, line: str) -> None:
        """OTP 는 6자리 숫자라 모양만으로는 차트번호·나이와 구분되지 않는다.

        그래서 **이름이 붙었을 때** 가린다. 마지막 케이스처럼 이름 없이 흘리는 코드가
        있으면 그건 호출부를 고쳐야 한다 — 아래 test_bare_six_digits_are_left_alone 참고.
        """
        cleaned = scrub(line)
        if "483920" in cleaned:
            assert line == "OTP 483920 sent", f"이름 붙은 OTP 가 남았다: {cleaned}"

    def test_rrn_never_survives(self) -> None:
        """우리는 주민번호를 수집하지 않는다. 그래도 흘러들면 지운다."""
        cleaned = scrub("resident 900101-2345678 detected")
        assert "2345678" not in cleaned
        assert "900101" in cleaned, "앞 여섯 자리는 생년월일이라 추적에 쓸 수 있다"


class TestPhoneKeepsLastFour:
    """전화번호는 지우지 않는다. 뒤 4자리는 남겨야 어느 건인지 따라간다."""

    @pytest.mark.parametrize("raw", ["010-1234-5678", "01012345678", "010 1234 5678", "010.1234.5678"], ids=repr)
    def test_middle_is_covered_and_tail_remains(self, raw: str) -> None:
        cleaned = mask_phone(raw)
        assert "1234" not in cleaned, f"가운데가 남았다: {cleaned}"
        assert cleaned.endswith("5678"), f"뒤 4자리가 사라졌다: {cleaned}"
        assert cleaned.startswith("010")

    def test_phone_inside_a_sentence(self) -> None:
        cleaned = scrub("sms to 010-9876-5432 failed")
        assert "9876" not in cleaned
        assert "5432" in cleaned


class TestFalsePositives:
    """너무 넓게 가리면 로그가 쓸모없어진다. 남아야 할 것은 남아야 한다."""

    def test_chart_number_survives(self) -> None:
        """차트번호는 의료진이 매일 보는 값이고 그것만으로는 환자를 못 연다."""
        assert "12345" in scrub("patient chart_no=12345 not found")

    def test_bare_six_digits_are_left_alone(self) -> None:
        """이름 없는 6자리는 OTP 인지 알 수 없다. 나이·개수·차트번호일 수 있다."""
        assert "483920" in scrub("processed 483920 rows")

    def test_short_identifiers_survive(self) -> None:
        """짧은 식별자까지 토큰으로 보면 visit_id · request_id 가 다 사라진다."""
        for keep in ("visit_id=8842", "request_id=a1b2c3d4"):
            assert keep in scrub(f"handling {keep}")

    def test_ordinary_words_survive(self) -> None:
        assert "안내문 생성 실패" in scrub("안내문 생성 실패 visit 8842")


class TestLoggerAppliesItAutomatically:
    """호출부가 잊어도 걸려야 한다 — 그것이 이 방식을 고른 이유다."""

    @staticmethod
    def _capture(name: str) -> tuple[logging.Logger, list[str]]:
        logger = setup_logger(name)
        written: list[str] = []

        class Sink(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                written.append(self.format(record))

        logger.addHandler(Sink())
        return logger, written

    def test_message_is_masked(self) -> None:
        logger, written = self._capture("mask-test-msg")
        logger.warning('login failed {"login_id": "staff01", "password": "Str0ng!Pass"}')
        assert "Str0ng!Pass" not in written[0]
        assert "staff01" in written[0], "누가 실패했는지는 남아야 원인을 찾는다"

    def test_format_args_are_masked(self) -> None:
        """민감한 값은 대개 메시지가 아니라 인자로 들어온다."""
        logger, written = self._capture("mask-test-args")
        logger.warning("token issued: %s", LINK_TOKEN)
        assert LINK_TOKEN not in written[0]

    def test_placeholders_survive_so_the_log_survives(self) -> None:
        """가리려다 기록을 없애면 안 된다.

        포맷 문자열을 그대로 훑으면 `token=%s` 의 `%s` 가 값으로 보여 함께 지워진다.
        그러면 `msg % args` 가 TypeError 를 내고 **로그가 통째로 사라진다.**
        실제로 처음 만들 때 이렇게 깨졌다.
        """
        logger, written = self._capture("mask-test-placeholder")
        logger.warning("issued patient link token=%s for visit %s", LINK_TOKEN, 8842)

        assert written, "로그가 아예 안 찍혔다 — 마스킹이 포맷을 깨뜨렸다"
        assert LINK_TOKEN not in written[0]
        assert "8842" in written[0], "가리지 않아도 될 값까지 사라졌다"
        assert "%s" not in written[0], "자리표시자가 그대로 남았다 — 포맷이 안 됐다"

    def test_percent_in_message_does_not_break(self) -> None:
        """인자 없이 `%` 가 든 메시지도 흔하다 — `진행률 50%` 같은 것."""
        logger, written = self._capture("mask-test-percent")
        logger.info("업로드 진행률 50% 완료")
        assert "50%" in written[0]

    def test_exception_args_are_masked(self) -> None:
        """exc_info 로 붙는 예외가 접속 정보를 담고 나가는 일이 실제로 있었다.

        KEY-19 헬스체크에서 DBConnectionError 가 host · user · db 를 그대로
        내보내던 것이 그 예다.
        """
        logger, written = self._capture("mask-test-exc")
        # 실제로 그렇듯 값은 변수에 담겨 온다. 소스에 박아 두면 트레이스백이
        # 소스 줄을 그대로 읽어 와서, 마스킹과 무관하게 남는다 — 아래 테스트 참고.
        password = "pw1234"
        try:
            raise ValueError(f"Can't connect: password={password} token={LINK_TOKEN}")
        except ValueError as exc:
            logger.warning("db check failed", exc_info=exc)
        joined = "".join(written)
        assert password not in joined
        assert LINK_TOKEN not in joined


class TestWhereMaskingCannotReach:
    """이 방식이 못 막는 자리. 알고 두는 것과 모르고 두는 것은 다르다."""

    def test_traceback_shows_the_source_line_itself(self) -> None:
        """트레이스백은 **소스 파일에서 그 줄을 읽어** 보여준다. 필터가 닿지 않는다.

        마스킹은 로그 레코드(메시지 · 인자 · 예외 인자)를 훑는 것이지
        소스 파일을 고치는 것이 아니다. 그래서 **소스에 비밀값이 박혀 있으면**
        예외가 날 때 그 줄이 그대로 찍힌다.

        고칠 곳은 필터가 아니라 소스다 — `test_secrets_not_committed.py` 가
        저장소에 비밀값이 들어오는 것을 따로 막는 이유가 이것이다.
        """
        import traceback

        try:
            # 값을 소스에 그대로 적는다 — 실제 사고가 이 모양이다.
            raise ValueError("planted-in-source-8fJ2kd")
        except ValueError:
            rendered = traceback.format_exc()

        # 소스 줄과 예외 메시지 줄, 두 곳에 나온다. 필터는 뒤의 것만 가릴 수 있다.
        assert rendered.count("planted-in-source-8fJ2kd") >= 2, (
            f"트레이스백이 소스 줄을 더는 안 읽는다면 좋은 소식이다 — 이 테스트를 지워라\n{rendered}"
        )
