"""KEY-264: Pilot 고정 OTP 좁은문 (env + 실행 플래그 이중 요구).

인수조건과 1:1 대응:
- 이중 플래그 둘 다 있어야 열림, 하나라도 없으면 기존과 동일하게 차단
  -> TestGuardRequiresBothFlags
- Pilot(ENV=prod + 이중 플래그)에서 000000 통과, 세션 발급
  -> TestOtpPassesThroughTheGate
- 좁은문 사용 시 감사로그 1건, OTP 값 미노출
  -> TestAuditLog
"""

import sys
import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.apis.v1.patient_otp_routers import _otp_service
from app.core.config import (
    PILOT_ALLOW_MOCK_OTP_ENV,
    PILOT_ALLOW_MOCK_OTP_FLAG,
    Config,
    Env,
    pilot_mock_otp_gate_open,
)
from app.main import app
from app.services.patient_otp import MockOtpDelivery, UnavailableOtpDelivery
from app.tests.auth_base import AuthTestCase
from app.tests.patient_links.test_patient_otp import LINK_TOKEN, make_link

MOCK_CODE = "000000"
PROD_SECRET = "syn-prod-secret-for-key264-tests"


def argv(*extra: str) -> list[str]:
    return ["pytest", *extra]


def make_prod_config() -> Config:
    return Config(
        ENV=Env.PROD,
        MOCK_OTP_CODE=MOCK_CODE,
        SECRET_KEY=PROD_SECRET,
        DB_PASSWORD="syn-test-db-password",
    )


class TestGuardRequiresBothFlags(unittest.TestCase):
    """env + 실행 플래그 둘 다 있어야 열린다."""

    def test_neither_flag_blocks_boot(self) -> None:
        with patch.dict("os.environ", {}, clear=False), patch.object(sys, "argv", argv()):
            self.assertFalse(pilot_mock_otp_gate_open())
            with self.assertRaises(ValueError):
                make_prod_config()

    def test_env_only_still_blocks_boot(self) -> None:
        with (
            patch.dict("os.environ", {PILOT_ALLOW_MOCK_OTP_ENV: "1"}),
            patch.object(sys, "argv", argv()),
        ):
            self.assertFalse(pilot_mock_otp_gate_open())
            with self.assertRaises(ValueError):
                make_prod_config()

    def test_flag_only_still_blocks_boot(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=False),
            patch.object(sys, "argv", argv(PILOT_ALLOW_MOCK_OTP_FLAG)),
        ):
            self.assertFalse(pilot_mock_otp_gate_open())
            with self.assertRaises(ValueError):
                make_prod_config()

    def test_both_flags_open_the_gate(self) -> None:
        with (
            patch.dict("os.environ", {PILOT_ALLOW_MOCK_OTP_ENV: "1"}),
            patch.object(sys, "argv", argv(PILOT_ALLOW_MOCK_OTP_FLAG)),
        ):
            self.assertTrue(pilot_mock_otp_gate_open())
            cfg = make_prod_config()
            self.assertEqual(cfg.MOCK_OTP_CODE, MOCK_CODE)


class TestAuditLog(unittest.TestCase):
    """좁은문이 열리면 감사로그 1건, OTP 값은 안 남는다."""

    def test_gate_open_logs_exactly_once_without_the_otp_value(self) -> None:
        with (
            patch.dict("os.environ", {PILOT_ALLOW_MOCK_OTP_ENV: "1"}),
            patch.object(sys, "argv", argv(PILOT_ALLOW_MOCK_OTP_FLAG)),
            self.assertLogs("ai_worker", level="WARNING") as logs,
        ):
            make_prod_config()

        gate_logs = [line for line in logs.output if "KEY-264" in line]
        self.assertEqual(len(gate_logs), 1)
        self.assertNotIn(MOCK_CODE, gate_logs[0])


class TestOtpPassesThroughTheGate(AuthTestCase):
    """ENV=prod + 이중 플래그면 000000 입력으로 인증이 통과하고 세션이 발급된다."""

    def setUp(self) -> None:
        super().setUp()
        import app.core as core_module

        env_patch = patch.object(core_module.config, "ENV", Env.PROD)
        code_patch = patch.object(core_module.config, "MOCK_OTP_CODE", MOCK_CODE)
        environ_patch = patch.dict("os.environ", {PILOT_ALLOW_MOCK_OTP_ENV: "1"})
        argv_patch = patch.object(sys, "argv", argv(PILOT_ALLOW_MOCK_OTP_FLAG))

        env_patch.start()
        self.addCleanup(env_patch.stop)
        code_patch.start()
        self.addCleanup(code_patch.stop)
        environ_patch.start()
        self.addCleanup(environ_patch.stop)
        argv_patch.start()
        self.addCleanup(argv_patch.stop)

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    def test_otp_service_returns_mock_delivery(self) -> None:
        service = _otp_service()
        self.assertIsInstance(service.delivery, MockOtpDelivery)
        self.assertEqual(service.fixed_otp_code, MOCK_CODE)

    async def test_fixed_code_passes_and_issues_session(self) -> None:
        await make_link()
        async with self.client() as c:
            issue = await c.post("/api/v1/patient-auth/otp/issue", json={"link_token": LINK_TOKEN})
            assert issue.status_code == 200

            verify = await c.post(
                "/api/v1/patient-auth/otp/verify",
                json={"link_token": LINK_TOKEN, "code": MOCK_CODE},
            )
            assert verify.status_code == 200
            assert verify.json()["verified"] is True
            assert "patient_session=" in verify.headers.get("set-cookie", "")


class TestOtpStillBlockedWithoutTheGate(unittest.TestCase):
    """일반 운영(ENV=prod, 플래그 없음) 회귀 없음 — otp 서비스는 그대로 막힌다."""

    def test_otp_service_returns_unavailable(self) -> None:
        import app.core as core_module

        with (
            patch.object(core_module.config, "ENV", Env.PROD),
            patch.object(core_module.config, "MOCK_OTP_CODE", MOCK_CODE),
            patch.dict("os.environ", {}, clear=False),
            patch.object(sys, "argv", argv()),
        ):
            service = _otp_service()
            self.assertIsInstance(service.delivery, UnavailableOtpDelivery)
