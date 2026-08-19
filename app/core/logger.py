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
