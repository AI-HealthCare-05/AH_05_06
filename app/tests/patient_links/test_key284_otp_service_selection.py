"""_otp_service()의 환경별 provider 선택 — KEY-284.

인수조건과 1:1 대응:
- mock과 solapi가 환경 설정만으로 전환되며 API 계약은 동일함
- Pilot/staging: 승인된 테스트 번호에서만 실제 solapi 선택 가능
- prod: 필수 자격증명과 안전 설정(좁은문)이 갖춰진 경우에만 실제 provider 선택
"""

import os
import sys
import unittest
from unittest.mock import patch

from pydantic import SecretStr

import app.core as core_module
from app.apis.v1.patient_otp_routers import _otp_service
from app.core.config import Env, SmsProvider
from app.services.patient_otp import (
    ApprovedPhonesOnlyDelivery,
    MockOtpDelivery,
    SolapiOtpDelivery,
    UnavailableOtpDelivery,
)


def argv(*extra: str) -> list[str]:
    return ["pytest", *extra]


class TestMockOtpCodeTakesPriority(unittest.TestCase):
    def test_mock_otp_code_selects_mock_delivery_regardless_of_sms_provider(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", "000000"),
            patch.object(core_module.config, "ENV", Env.LOCAL),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, MockOtpDelivery)
        self.assertEqual(service.fixed_otp_code, "000000")


class TestDefaultWithoutSolapiConfigured(unittest.TestCase):
    def test_mock_provider_without_mock_otp_code_stays_unavailable(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.MOCK),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, UnavailableOtpDelivery)


class TestNonProdSolapiIsRestrictedToApprovedNumbers(unittest.TestCase):
    def test_non_prod_solapi_wraps_in_the_approved_phones_gate(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "ENV", Env.LOCAL),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, ApprovedPhonesOnlyDelivery)
        self.assertIsInstance(service.delivery._delivery, SolapiOtpDelivery)  # type: ignore[attr-defined]

    def test_approved_test_phones_env_populates_the_allowlist(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "ENV", Env.DEV),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.object(core_module.config, "OTP_APPROVED_TEST_PHONES", SecretStr("01011112222, 01033334444")),
        ):
            service = _otp_service()

        self.assertEqual(
            service.delivery._approved_phones,  # type: ignore[attr-defined]
            frozenset({"01011112222", "01033334444"}),
        )


class TestProdRequiresItsOwnNarrowGate(unittest.TestCase):
    """SMS_PROVIDER=solapi + 자격증명만으로는 prod에서 실제 발송이 켜지지 않는다."""

    def test_prod_without_the_gate_stays_unavailable(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "ENV", Env.PROD),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.dict(os.environ, {}, clear=False),
            patch.object(sys, "argv", argv()),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, UnavailableOtpDelivery)

    def test_env_var_alone_does_not_open_it(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "ENV", Env.PROD),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.dict(os.environ, {"OTP_SOLAPI_PROD_ENABLED": "1"}),
            patch.object(sys, "argv", argv()),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, UnavailableOtpDelivery)

    def test_cli_flag_alone_does_not_open_it(self) -> None:
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "ENV", Env.PROD),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.dict(os.environ, {}, clear=False),
            patch.object(sys, "argv", argv("--otp-confirm-solapi-prod")),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, UnavailableOtpDelivery)

    def test_both_together_open_it_without_the_test_phone_wrapper(self) -> None:
        """prod는 실제 환자에게 나가야 하므로 승인 번호 목록으로 좁히지 않는다."""
        with (
            patch.object(core_module.config, "MOCK_OTP_CODE", ""),
            patch.object(core_module.config, "ENV", Env.PROD),
            patch.object(core_module.config, "SMS_PROVIDER", SmsProvider.SOLAPI),
            patch.dict(os.environ, {"OTP_SOLAPI_PROD_ENABLED": "1"}),
            patch.object(sys, "argv", argv("--otp-confirm-solapi-prod")),
        ):
            service = _otp_service()

        self.assertIsInstance(service.delivery, SolapiOtpDelivery)
