import logging
import sys
import traceback

from app.core.masking import scrub


class MaskingFilter(logging.Filter):
    """로그로 나가는 모든 것을 한 번 훑는다 — KEY-11.

    호출부에서 가리는 방식은 언젠가 빠뜨린다. 사람이 기억해야 하고,
    새로 들어온 사람은 규칙이 있는지도 모른다. 그래서 **나가는 길목**에 둔다.

    포맷 인자와 예외 메시지까지 훑는 이유는, 대개 민감한 값이
    `logger.warning("login failed: %s", payload)` 처럼 인자로 들어오기 때문이다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # **포맷을 먼저 끝내고 그 결과를 가린다.**
        #
        # 포맷 문자열을 그대로 훑으면 `token=%s` 의 `%s` 가 값으로 보여 함께 지워진다.
        # 그러면 자리표시자가 사라져 `msg % args` 가 TypeError 를 내고 **로그가 통째로
        # 사라진다.** 가리려다 기록을 없애는 셈이라, 완성된 문장을 가린다.
        if isinstance(record.msg, str):
            record.msg = scrub(record.getMessage())
            record.args = ()

        # exc_info=e 로 붙는 예외도 트레이스백째 찍힌다. DBConnectionError 처럼
        # 접속 정보를 담은 예외가 그대로 새어 나간다.
        #
        # **예외 객체 자체는 건드리지 않는다.** `exc.args` 를 고치면 그 예외가 다시
        # 던져질 때도, API 응답에 쓰일 때도 바뀐 값이 나간다 — 로그를 가리려다
        # 애플리케이션 동작을 바꾸는 셈이다.
        #
        # 대신 **렌더링 결과만** 미리 채운다. `logging.Formatter` 는 `exc_text` 가
        # 이미 있으면 그걸 그대로 쓰므로, 핸들러가 몇 개든 같은 결과를 본다.
        if record.exc_info and record.exc_info[0] is not None and not record.exc_text:
            record.exc_text = scrub("".join(traceback.format_exception(*record.exc_info)).rstrip())

        return True


class AccessLogMaskingFilter(logging.Filter):
    """`uvicorn.access` 전용 가리개 — KEY-155.

    **`MaskingFilter` 를 그대로 쓰면 access 로그가 깨진다.** uvicorn 의
    `AccessFormatter.formatMessage()` 가 `record.args` 를 다섯 개로 풀어 쓴다.

        client_addr, method, full_path, http_version, status_code = record.args

    `MaskingFilter` 는 포맷을 끝내고 `args` 를 비우는데, 그러면 여기서
    `ValueError` 가 나고 **줄이 통째로 「Logging error」 로 떨어진다.** 원문은
    안 새지만 메서드·경로·상태 코드도 함께 사라진다 — 가리려다 관측을 잃는다.

    그래서 **자리 수를 지키고 값만 가린다.** 문자열 인자만 훑고 나머지는 그대로
    둔다. `status_code` 는 `int` 라 손대지 않아야 뒤에서 `int()` 가 성립한다.

    가려지는 것은 사실상 `full_path` 하나다 — 환자 링크 토큰이 `GET /guides/{token}`
    으로, OTP 가 쿼리스트링으로 실려 오는 자리다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(scrub(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            # 인자 없이 문장만 찍는 줄도 있다.
            record.msg = scrub(record.getMessage())
        return True


#: 서버가 **스스로** 찍는 로그. 우리 코드가 아니라 uvicorn 이 부르는 로거들이라
#: `setup_logger()` 가 만든 가리개가 안 붙어 있다.
#:
#: `uvicorn.access` 는 요청 줄을 그대로 찍는다 — **경로와 쿼리스트링째** 다.
#: 환자 링크 토큰은 URL 에 실려 올 수밖에 없고(`GET /guides/{token}`), 그러면
#: 원문이 로그에 남는다. `uvicorn.error` 도 기동·예외 문장을 찍으므로 함께 건다.
#: `uvicorn.access` 만 전용 가리개를 쓴다 — 위 클래스 주석 참고.
#: `uvicorn.error` 는 보통 로거라 공통 가리개로 충분하다.
SERVER_LOGGERS: tuple[tuple[str, type[logging.Filter]], ...] = (
    ("uvicorn.access", AccessLogMaskingFilter),
    ("uvicorn.error", MaskingFilter),
)


def mask_server_logs() -> None:
    """uvicorn 이 쓰는 로거에도 같은 가리개를 붙인다 — KEY-155.

    **핸들러가 아니라 로거에 붙인다.** 핸들러에 붙이면 누가 핸들러를 하나 더
    다는 순간 그쪽으로 새어 나간다 — `setup_logger()` 가 같은 이유로 그렇게 한다.

    두 번 불러도 하나만 붙는다. 앱이 여러 번 임포트되는 자리(테스트·reload)가
    있어서, 같은 필터가 쌓이면 한 줄을 여러 번 훑게 된다.
    """
    for name, filter_type in SERVER_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, filter_type) for f in logger.filters):
            logger.addFilter(filter_type())


def setup_logger(
    name: str = "ai_worker",
    level: int = logging.INFO,
) -> logging.Logger:
    _logger = logging.getLogger(name)

    # 중복 핸들러 방지 (중요)
    if _logger.handlers:
        return _logger

    _logger.setLevel(level)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")

    # 콘솔 출력
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    _logger.addHandler(console_handler)
    # 마스킹은 로거에 붙인다 — 핸들러에 붙이면 핸들러를 하나 더 다는 순간 새어 나간다
    _logger.addFilter(MaskingFilter())
    _logger.propagate = False  # root logger로 중복 전달 방지

    return _logger


# 앱 전역에서 사용할 로거
default_logger = setup_logger()
