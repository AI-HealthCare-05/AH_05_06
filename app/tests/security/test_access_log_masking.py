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

from app.core.logger import AccessLogMaskingFilter, mask_server_logs
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
    AccessLogMaskingFilter().filter(record)
    assert isinstance(record.args, tuple)
    return str(record.args[2])


class TestSecretsInTheUrlDisappear:
    """URL 에 실려 오는 것들. 링크 토큰은 **경로**에, OTP 는 **쿼리스트링**에 온다."""

    @pytest.mark.parametrize(
        ("path", "secret"),
        [
            # P1-1~P1-5 환자 링크 — 토큰이 경로에 있다. 키 이름이 없어 값 모양으로 잡는다.
            ("/api/v1/guides/kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x", "kQ7bXm2pR9"),
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
        AccessLogMaskingFilter().filter(record)

        assert isinstance(record.args, tuple)
        client, method, path, version, status = record.args  # uvicorn 이 하는 그대로
        assert (client, method, version, status) == ("127.0.0.1:51234", "GET", "1.1", 200)
        assert REDACTED in str(path)

    def test_the_status_code_stays_a_number(self) -> None:
        """`int()` 로 다시 읽히는 자리다. 문자열로 바꾸면 포맷터가 죽는다."""
        record = access_record("/api/v1/health")
        AccessLogMaskingFilter().filter(record)
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

    def test_mask_server_logs_attaches_to_uvicorn_access(self) -> None:
        mask_server_logs()
        attached = logging.getLogger("uvicorn.access").filters
        assert any(isinstance(f, AccessLogMaskingFilter) for f in attached)

    def test_calling_it_twice_does_not_stack(self) -> None:
        """앱이 여러 번 임포트되는 자리가 있다. 쌓이면 한 줄을 여러 번 훑는다."""
        mask_server_logs()
        mask_server_logs()
        attached = logging.getLogger("uvicorn.access").filters
        assert sum(isinstance(f, AccessLogMaskingFilter) for f in attached) == 1
