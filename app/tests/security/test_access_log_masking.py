"""uvicorn 이 스스로 찍는 access 로그에 민감정보가 남지 않는가 — KEY-155.

인수조건: 「uvicorn.access 에 민감정보가 포함된 요청이 기록돼도 원문이 남지
않음」·「일반 access log 의 메서드·안전한 경로 정보·상태 코드는 확인 가능함」

`#75`(KEY-48) 검수에서 나온 후속 공백이다. 우리 코드가 부르는 로거에는
`MaskingFilter` 가 붙어 있었지만, **uvicorn 이 부르는 로거에는 없었다.**
환자 링크 토큰은 URL 에 실려 올 수밖에 없어서(`GET /guides/{token}`) 그대로
남았다.

여기 쓰는 값은 전부 **합성**이다 — 실제 토큰·OTP·전화번호가 아니다.
"""

import logging

import pytest

from app.core.logger import SERVER_LOGGERS, ServerLogMaskingFilter, mask_server_logs
from app.core.masking import REDACTED

#: uvicorn 이 access 레코드에 싣는 다섯 자리.
#: `AccessFormatter.formatMessage()` 가 이 순서로 풀어 쓴다.
ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'


def access_record(full_path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=ACCESS_FORMAT,
        args=("127.0.0.1:51234", "GET", full_path, "1.1", 200),
        exc_info=None,
    )


def scrubbed_path(full_path: str) -> str:
    record = access_record(full_path)
    ServerLogMaskingFilter().filter(record)
    assert isinstance(record.args, tuple)
    return str(record.args[2])


class TestSecretsInTheUrlDisappear:
    """URL 에 실려 오는 것들. 링크 토큰은 **경로**에, OTP 는 **쿼리스트링**에 온다."""

    @pytest.mark.parametrize(
        ("path", "secret"),
        [
            # P1-1~P1-5 환자 링크 — 토큰이 경로에 있다. 키 이름이 없어 값 모양으로 잡는다.
            ("/api/v1/guides/kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x", "kQ7bXm2pR9"),
            # KEY-151 D+7도 같은 원문 토큰을 경로에 쓰므로 같은 가리개를 반드시 지난다.
            ("/api/v1/checkins/kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x", "kQ7bXm2pR9"),
            # OTP 는 여섯 자리 숫자일 때만 잡는다 — `status_code` 같은 이름을 삼키지 않도록
            ("/api/v1/links/verify?code=482913", "482913"),
            ("/api/v1/auth/login?password=Str0ng%21Pass", "Str0ng"),
            ("/api/v1/x?access_token=eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxMn0.s0m3S1g", "eyJhbGci"),
            ("/api/v1/x?refresh_token=kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x", "kQ7bXm2pR9"),
        ],
    )
    def test_the_original_is_gone(self, path: str, secret: str) -> None:
        masked = scrubbed_path(path)
        assert secret not in masked, f"access log 에 원문이 남았다: {masked}"
        assert REDACTED in masked


class TestTheLineStaysUsable:
    """가리려다 관측을 잃으면 안 된다.

    처음에는 공통 `MaskingFilter` 를 그대로 붙였는데, 그것이 포맷을 끝내고
    `record.args` 를 비운다. uvicorn 포맷터는 그 자리를 **다섯 개로 풀어 쓰므로**
    `ValueError` 가 나고 줄이 통째로 「Logging error」 로 떨어졌다 —
    **원문은 안 새지만 메서드·경로·상태 코드도 함께 사라진다.**
    """

    def test_the_five_slots_survive(self) -> None:
        record = access_record("/api/v1/guides/kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x")
        ServerLogMaskingFilter().filter(record)

        assert isinstance(record.args, tuple)
        client, method, path, version, status = record.args  # uvicorn 이 하는 그대로
        assert (client, method, version, status) == ("127.0.0.1:51234", "GET", "1.1", 200)
        assert REDACTED in str(path)

    def test_the_status_code_stays_a_number(self) -> None:
        """`int()` 로 다시 읽히는 자리다. 문자열로 바꾸면 포맷터가 죽는다."""
        record = access_record("/api/v1/health")
        ServerLogMaskingFilter().filter(record)
        assert isinstance(record.args, tuple)
        assert isinstance(record.args[4], int)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/health",
            "/api/v1/patients?keyword=test&limit=20",
            "/api/v1/visits/8801",
            "/api/v1/patients?cursor=eyJ2IjoxfQ",  # 커서는 비밀이 아니다
        ],
    )
    def test_ordinary_requests_are_untouched(self, path: str) -> None:
        assert scrubbed_path(path) == path, "일반 요청이 가려지면 운영 관찰이 안 된다"


class TestTheFilterIsActuallyAttached:
    """붙이는 것을 잊으면 위의 검사가 전부 헛돈다 — 필터 자체는 잘 도니까."""

    @pytest.mark.parametrize("name", SERVER_LOGGERS)
    def test_mask_server_logs_attaches_to_every_server_logger(self, name: str) -> None:
        mask_server_logs()
        attached = logging.getLogger(name).filters
        assert any(isinstance(f, ServerLogMaskingFilter) for f in attached)

    @pytest.mark.parametrize("name", SERVER_LOGGERS)
    def test_calling_it_twice_does_not_stack(self, name: str) -> None:
        """앱이 여러 번 임포트되는 자리가 있다. 쌓이면 한 줄을 여러 번 훑는다."""
        mask_server_logs()
        mask_server_logs()
        attached = logging.getLogger(name).filters
        assert sum(isinstance(f, ServerLogMaskingFilter) for f in attached) == 1


class TestUvicornStartupLinesStayReadable:
    """`uvicorn.error` 도 인자를 나중에 한 번 더 쓴다 — `#85` 리뷰(이희진).

    `ColourizedFormatter.formatMessage()` 는 `use_colors=True` 일 때
    `color_message` 로 `record.msg` 를 덮고 `getMessage()` 를 **다시** 부른다.
    앞에서 `args` 를 비워 두면 재대입이 스킵되고 `%d`·`%s` 가 그대로 남는다 —
    **PID·호스트·포트가 사라진다.** 가리려다 관측을 잃는 자리다.
    """

    @staticmethod
    def _rendered(msg: str, args: tuple[object, ...], color: str) -> str:
        record = logging.LogRecord(
            name="uvicorn.error",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )
        record.__dict__["color_message"] = color
        ServerLogMaskingFilter().filter(record)
        # 포맷터가 하는 일을 그대로 흉내낸다 — msg 를 덮고 다시 렌더링한다.
        record.msg = record.__dict__["color_message"]
        return record.getMessage()

    def test_the_pid_survives(self) -> None:
        line = self._rendered("Started server process [%d]", (1234,), "Started server process [%d]")
        assert "1234" in line
        assert "%d" not in line

    def test_the_banner_keeps_host_and_port(self) -> None:
        line = self._rendered(
            "Uvicorn running on %s://%s:%d (Press CTRL+C to quit)",
            ("http", "127.0.0.1", 8000),
            "Uvicorn running on %s://%s:%d (Press CTRL+C to quit)",
        )
        assert "http://127.0.0.1:8000" in line
        assert "%s" not in line and "%d" not in line


class TestLinesWithoutArgumentsAreMaskedToo:
    """인자 없이 문장만 찍는 줄 — `#85` 리뷰(이희진).

    `record.args` 는 이때 `None` 이 아니라 **빈 튜플**이다. 타입으로 가르면
    `()` 도 튜플이라 인자 가지가 먹고, 문장을 가리는 가지는 영영 안 돈다.
    그러면 문장에 박힌 토큰이 **그대로 새어 나간다.**
    """

    TOKEN = "kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x"

    def _emitted(self, message: str) -> logging.LogRecord:
        seen: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                seen.append(record)

        logger = logging.getLogger("test.server.noargs")
        logger.handlers = [Capture()]
        logger.filters = [ServerLogMaskingFilter()]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.info(message)
        return seen[-1]

    def test_args_is_an_empty_tuple_not_none(self) -> None:
        """이 검사가 위 두 검사의 전제다. 전제가 바뀌면 여기서 먼저 깨진다."""
        record = self._emitted("아무 문장")
        assert record.args == ()
        assert isinstance(record.args, tuple)

    def test_a_token_in_a_bare_sentence_is_masked(self) -> None:
        record = self._emitted(f"patient link https://x/guides/{self.TOKEN}")
        assert self.TOKEN not in record.getMessage()
        assert REDACTED in record.getMessage()

    def test_color_message_is_masked_as_well(self) -> None:
        """한쪽만 가리면 **터미널에서만** 원문이 보인다 — 가장 놓치기 쉬운 자리다."""
        record = logging.LogRecord(
            name="uvicorn.error",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=f"link {self.TOKEN}",
            args=(),
            exc_info=None,
        )
        record.__dict__["color_message"] = f"link {self.TOKEN}"
        ServerLogMaskingFilter().filter(record)
        assert self.TOKEN not in record.msg
        assert self.TOKEN not in record.__dict__["color_message"]


class TestExceptionsStayMasked:
    """`uvicorn.error` 는 예외도 트레이스백째 찍는다.

    이 자리는 원래 공통 `MaskingFilter` 가 맡고 있었다. 전용 가리개로 바꾸면서
    **함께 옮겨 오지 않으면 조용히 빠진다** — 그래서 검사로 붙잡는다.
    """

    def test_traceback_is_scrubbed(self) -> None:
        token = "kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x"
        try:
            raise RuntimeError(f"connect failed for {token}")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                name="uvicorn.error",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="unhandled",
                args=(),
                exc_info=sys.exc_info(),
            )
        ServerLogMaskingFilter().filter(record)
        assert record.exc_text is not None
        assert token not in record.exc_text
        assert REDACTED in record.exc_text
