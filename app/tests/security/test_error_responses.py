"""오류 응답에 민감정보가 실려 나가지 않는가 — KEY-11.

인수조건: 「예외 응답의 민감정보 제거」

**로그보다 멀리 간다.** 오류 응답은 사용자 브라우저 · 프록시 · 에러 추적 서비스에
그대로 남는다. 로그는 우리만 보지만 이건 아니다.
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.error_handlers import register_error_handlers

JWT_SAMPLE = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxMn0.s0m3S1gnatur3"
LINK_TOKEN = "kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x"


class SignUp(BaseModel):
    email: str = Field(pattern=r".+@.+")
    password: str = Field(min_length=8)
    otp: str = Field(min_length=6, max_length=6)


def build_app() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/signup")
    def signup(_: SignUp) -> dict[str, bool]:  # pragma: no cover - 검증에서 걸린다
        return {"ok": True}

    @app.get("/leaky-detail")
    def leaky() -> None:
        raise HTTPException(400, detail=f"invalid token {JWT_SAMPLE}")

    @app.get("/leaky-phone")
    def leaky_phone() -> None:
        raise HTTPException(409, detail="이미 등록된 번호입니다: 010-1234-5678")

    @app.get("/boom")
    def boom() -> None:
        raise ValueError(f"Can't connect: password=n0t-a-real-pw token={LINK_TOKEN}")

    return TestClient(app, raise_server_exceptions=False)


class TestValidationErrorsDoNotEchoInput:
    """FastAPI 기본은 `input` 에 **사용자가 보낸 값을 그대로** 담는다.

    비밀번호가 여덟 자 미만이면 그 비밀번호가 응답에 실려 나간다.
    """

    def test_password_is_not_echoed(self) -> None:
        client = build_app()
        response = client.post("/signup", json={"email": "a@b.c", "password": "abc", "otp": "483920"})

        assert response.status_code == 422
        assert "abc" not in response.text, f"비밀번호가 응답에 남았다: {response.text}"

    def test_otp_is_not_echoed(self) -> None:
        client = build_app()
        response = client.post("/signup", json={"email": "a@b.c", "password": "LongEnough1!", "otp": "12"})

        assert response.status_code == 422
        assert "12" not in response.json()["detail"][0].get("msg", ""), "OTP 조각이 남았다"
        assert all("input" not in e for e in response.json()["detail"])

    def test_it_still_says_what_is_wrong(self) -> None:
        """가리기만 하고 원인을 안 알려 주면 화면이 안내를 못 만든다.

        어느 필드(`loc`)가 무슨 규칙(`msg`)을 어겼는지는 남아야 한다.
        """
        client = build_app()
        errors = client.post("/signup", json={"email": "a@b.c", "password": "abc", "otp": "483920"}).json()["detail"]

        target = next(e for e in errors if e["loc"][-1] == "password")
        assert target["type"] == "string_too_short"
        assert "8" in target["msg"], "최소 길이를 알려 줘야 화면이 「8자 이상」이라고 쓴다"

    def test_value_embedded_in_message_is_scrubbed(self) -> None:
        """어떤 규칙은 `msg` 안에 값을 섞어 넣는다."""
        client = build_app()
        response = client.post("/signup", json={"email": JWT_SAMPLE, "password": "LongEnough1!", "otp": "483920"})
        assert JWT_SAMPLE not in response.text

    def test_custom_validator_errors_still_serialize(self) -> None:
        """`AfterValidator` 가 던진 `ValueError` 는 `ctx` 에 **객체 그대로** 들어온다.

        문자열로 바꾸지 않으면 직렬화가 실패해 **오류 응답 자체가 500이 된다.**
        가리려다 응답을 깨뜨리는 셈이라, 실제로 기존 회원가입 테스트가 이걸 잡았다.
        """
        from typing import Annotated

        from pydantic import AfterValidator

        def must_be_strong(value: str) -> str:
            raise ValueError("비밀번호에는 대문자·소문자·특수문자·숫자가 각 하나씩 필요합니다.")

        class Strict(BaseModel):
            password: Annotated[str, AfterValidator(must_be_strong)]

        app = FastAPI()
        register_error_handlers(app)

        @app.post("/strict")
        def strict(_: Strict) -> dict[str, bool]:  # pragma: no cover - 검증에서 걸린다
            return {"ok": True}

        response = TestClient(app, raise_server_exceptions=False).post("/strict", json={"password": "weak"})

        assert response.status_code == 422, f"응답이 깨졌다: {response.status_code}"
        assert "weak" not in response.text, "입력값이 남았다"
        assert "대문자" in response.text, "왜 막혔는지는 알려 줘야 화면이 안내를 만든다"


class TestHttpExceptionDetailIsScrubbed:
    """`detail` 은 개발자가 쓴 문장이 그대로 나간다."""

    def test_token_in_detail_disappears(self) -> None:
        response = build_app().get("/leaky-detail")
        assert response.status_code == 400
        assert JWT_SAMPLE not in response.text
        assert "invalid token" in response.text, "무슨 오류인지는 남아야 한다"

    def test_phone_keeps_only_last_four(self) -> None:
        response = build_app().get("/leaky-phone")
        assert "1234-5678" not in response.text
        assert "5678" in response.text, "뒤 4자리는 남아야 본인 번호인지 알아본다"
        assert "이미 등록된 번호입니다" in response.text


class TestUnhandledErrorsStaySilent:
    def test_500_says_nothing(self) -> None:
        """FastAPI 기본이 이미 안전하다. 바뀌면 여기서 걸린다."""
        response = build_app().get("/boom")
        assert response.status_code == 500
        assert "n0t-a-real-pw" not in response.text
        assert LINK_TOKEN not in response.text
        assert "MySQL" not in response.text


class TestRealAppHasThemRegistered:
    """만들어 놓고 안 붙이면 소용없다."""

    def test_app_registers_handlers(self) -> None:
        from fastapi.exceptions import RequestValidationError
        from starlette.exceptions import HTTPException as StarletteHTTPException

        from app.main import app

        assert RequestValidationError in app.exception_handlers
        assert StarletteHTTPException in app.exception_handlers


class TestOcrErrorHandlerIsAlsoScrubbed:
    """OCR 오류 핸들러는 `register_error_handlers()` 경로를 안 거친다 — KEY-48.

    지금은 `OcrApiError.message` 가 전부 고정 문구지만, 벤더 원문을 그대로
    실어 던지는 코드가 나중에 생겨도 여기서 걸려야 한다.
    """

    async def test_message_is_scrubbed(self) -> None:
        from app.main import ocr_api_error_handler
        from app.ocr.errors import OcrApiError

        exc = OcrApiError(502, "VENDOR_ERROR", f"upstream said token={LINK_TOKEN}")
        response = await ocr_api_error_handler(None, exc)

        assert LINK_TOKEN not in bytes(response.body).decode()
