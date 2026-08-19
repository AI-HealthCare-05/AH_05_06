import logging
import sys

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

        # exc_info=e 로 붙는 예외의 인자도 로그에 그대로 찍힌다.
        # 여기서 손대지 않으면 DBConnectionError 처럼 접속 정보를 담은 예외가 새어 나간다.
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            if exc.args:
                exc.args = tuple(scrub(a) if isinstance(a, str) else a for a in exc.args)

        return True


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
