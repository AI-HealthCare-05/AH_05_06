"""민감정보가 정상·오류 응답과 로그에 노출되지 않는지 검증한다 — KEY-25.

마스킹 함수의 세부 정규식은 ``test_masking.py``가 검증한다. 이 파일은 PR에서
빠르게 확인할 수 있도록 실제 노출 경로(응답 모델, 검증 오류, HTTP 오류, 로그)를
하나의 회귀 매트릭스로 묶는다.
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.error_handlers import register_error_handlers
from app.core.logger import setup_logger
from app.dtos.auth import StaffLoginResponse, TokenRefreshResponse

PASSWORD = "Synthetic12!"
OTP = "483920"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdGFmZl9pZCI6MX0.syntheticSignature"
PATIENT_LINK_TOKEN = "kQ7bXm2pR9tLvN4wZ8cA1dF6gH3jK5nP0qS7uY2eB4x"
PHONE = "010-1234-5678"
RRN = "900101-2345678"


class SensitiveRequest(BaseModel):
    password: str = Field(min_length=12)
    otp: str = Field(min_length=6, max_length=6)


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/normal")
    def normal(_: SensitiveRequest) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/error")
    def error() -> None:
        raise HTTPException(
            400,
            detail=(
                f"password={PASSWORD} otp={OTP} token={PATIENT_LINK_TOKEN} "
                f"authorization=Bearer-{JWT} phone={PHONE} rrn={RRN}"
            ),
        )

    return TestClient(app, raise_server_exceptions=False)


def _assert_secrets_absent(text: str) -> None:
    for secret in (PASSWORD, OTP, JWT, PATIENT_LINK_TOKEN, "1234-5678", "2345678"):
        assert secret not in text


class TestNormalResponses:
    def test_request_secrets_are_not_echoed(self) -> None:
        response = _client().post("/normal", json={"password": PASSWORD, "otp": OTP})

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        _assert_secrets_absent(response.text)

    def test_auth_success_models_only_expose_contract_fields(self) -> None:
        """액세스 토큰은 로그인·갱신 성공 응답에서만 허용된 계약 필드다."""
        assert set(StaffLoginResponse.model_fields) == {"access_token", "must_change_password"}
        assert set(TokenRefreshResponse.model_fields) == {"access_token"}


class TestErrorResponses:
    def test_validation_error_does_not_echo_input(self) -> None:
        leaked_password = "RawPw7!"
        response = _client().post("/normal", json={"password": leaked_password, "otp": "12"})

        assert response.status_code == 422
        assert all("input" not in error for error in response.json()["detail"])
        assert leaked_password not in response.text

    def test_http_error_scrubs_secrets_and_patient_identifiers(self) -> None:
        response = _client().get("/error")

        assert response.status_code == 400
        _assert_secrets_absent(response.text)
        assert "5678" in response.text, "전화번호는 추적용 뒤 4자리만 남긴다"


class TestApplicationLogs:
    def test_message_and_exception_paths_are_scrubbed(self) -> None:
        logger = setup_logger("key25-sensitive-regression")
        written: list[str] = []

        class Sink(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                written.append(self.format(record))

        logger.addHandler(Sink())
        logger.warning(
            "auth failed password=%s otp=%s token=%s phone=%s patient_id=%s",
            PASSWORD,
            OTP,
            PATIENT_LINK_TOKEN,
            PHONE,
            1001,
        )
        try:
            raise ValueError(f"authorization={JWT} rrn={RRN}")
        except ValueError as exc:
            logger.exception("request failed", exc_info=exc)

        output = "\n".join(written)
        _assert_secrets_absent(output)
        assert "patient_id=1001" in output, "내부 추적 ID는 보안 토큰이 아니므로 유지한다"
        assert "5678" in output
