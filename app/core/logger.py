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


class ServerLogMaskingFilter(logging.Filter):
    """uvicorn 이 **스스로** 찍는 로그 전용 가리개 — KEY-155.

    **공통 `MaskingFilter` 를 쓰면 uvicorn 로그가 깨진다.** 그것은 포맷을 끝내고
    `record.args` 를 비우는데, uvicorn 은 그 뒤에 인자를 **한 번 더** 쓴다.

        AccessFormatter.formatMessage()      args 를 다섯 개로 풀어 쓴다
        ColourizedFormatter.formatMessage()  color_message 로 msg 를 덮고
                                             getMessage() 를 다시 부른다

    비어 버린 args 로는 둘 다 성립하지 않는다. `uvicorn.access` 는 `ValueError` 로
    줄이 통째로 「Logging error」가 되고, `uvicorn.error` 는 `%d`·`%s` 가 그대로
    남아 **PID·호스트·포트가 사라진다.** 가리려다 관측을 잃는다.

        Started server process [%d]
        Uvicorn running on %s://%s:%d (Press CTRL+C to quit)

    그래서 **자리 수를 지키고 값만 가린다.**

    인자가 있으면 **포맷 문자열은 손대지 않는다.** `token=%s` 를 훑으면 `%s` 가
    값으로 보여 함께 지워지고, 자리표시자가 사라지면 `msg % args` 가 깨진다 —
    `MaskingFilter` 주석이 같은 이유를 적어 두었다. 민감한 값은 **인자로** 들어오지
    개발자가 쓴 포맷 문자열에 박히지 않는다.

    인자가 없을 때만 문장 자체를 가린다. 이때 `color_message` 도 함께 가린다 —
    `ColourizedFormatter` 가 그것으로 `msg` 를 덮어쓰므로, 한쪽만 가리면 터미널에서
    원문이 그대로 보인다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(scrub(a) if isinstance(a, str) else a for a in record.args)
        else:
            # 인자 없이 문장만 찍는 줄. **`record.args` 는 이때 `None` 이 아니라 빈
            # 튜플이다** — 타입으로 가르면 `()` 도 튜플이라 위 가지가 먹고, 여기는
            # 영영 안 돈다. 그러면 문장에 박힌 토큰이 그대로 새어 나간다.
            if isinstance(record.msg, str):
                record.msg = scrub(record.msg)
            color = record.__dict__.get("color_message")
            if isinstance(color, str):
                record.__dict__["color_message"] = scrub(color)

        # 예외는 트레이스백째 찍힌다 — `uvicorn.error` 가 바로 그 자리다.
        # `MaskingFilter` 와 같은 이유로 **예외 객체는 건드리지 않고** 렌더링
        # 결과만 미리 채운다.
        if record.exc_info and record.exc_info[0] is not None and not record.exc_text:
            record.exc_text = scrub("".join(traceback.format_exception(*record.exc_info)).rstrip())

        return True


#: 서버가 **스스로** 찍는 로그. 우리 코드가 아니라 uvicorn 이 부르는 로거들이라
#: `setup_logger()` 가 만든 가리개가 안 붙어 있다.
#:
#: `uvicorn.access` 는 요청 줄을 그대로 찍는다 — **경로와 쿼리스트링째** 다.
#: 환자 링크 토큰은 URL 에 실려 올 수밖에 없고(`GET /guides/{token}`), 그러면
#: 원문이 로그에 남는다. `uvicorn.error` 도 기동·예외 문장을 찍으므로 함께 건다.
#:
#: **둘 다 같은 가리개를 쓴다.** 포맷터가 인자를 한 번 더 쓰는 것이 양쪽 공통이라,
#: 공통 `MaskingFilter` 는 어느 쪽에도 쓸 수 없다 — 위 클래스 주석 참고.
SERVER_LOGGERS: tuple[str, ...] = ("uvicorn.access", "uvicorn.error")


def mask_server_logs() -> None:
    """uvicorn 이 쓰는 로거에도 같은 가리개를 붙인다 — KEY-155.

    **핸들러가 아니라 로거에 붙인다.** 핸들러에 붙이면 누가 핸들러를 하나 더
    다는 순간 그쪽으로 새어 나간다 — `setup_logger()` 가 같은 이유로 그렇게 한다.

    두 번 불러도 하나만 붙는다. 앱이 여러 번 임포트되는 자리(테스트·reload)가
    있어서, 같은 필터가 쌓이면 한 줄을 여러 번 훑게 된다.
    """
    for name in SERVER_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, ServerLogMaskingFilter) for f in logger.filters):
            logger.addFilter(ServerLogMaskingFilter())


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
