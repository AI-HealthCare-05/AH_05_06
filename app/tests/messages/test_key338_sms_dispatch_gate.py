"""KEY-338: 예약 문자 실발송 좁은문 (env + 실행 플래그 이중 요구).

인수조건과 1:1 대응:
- SMS_PROVIDER=solapi에서 스위치 중 하나라도 없으면 안 열린다
  -> TestGuardRequiresBothFlags
- 둘 다 있어야 열린다
  -> TestGuardRequiresBothFlags.test_both_flags_open_the_gate
- ENV로 안 가른다 — prod든 dev든 같은 판정
  -> TestGuardIgnoresEnv
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import (
    SMS_DISPATCH_ENABLED_ENV,
    SMS_DISPATCH_ENABLED_FLAG,
    SmsProvider,
    sms_dispatch_gate_open,
)


def argv(*extra: str) -> list[str]:
    return ["python", "-m", "ai_worker.main", *extra]


class TestGuardRequiresBothFlags(unittest.TestCase):
    """env + 실행 플래그 둘 다 있어야 열린다 — OTP 좁은문과 같은 모양."""

    def test_neither_flag_blocks(self) -> None:
        with patch.dict("os.environ", {}, clear=False), patch.object(sys, "argv", argv()):
            assert sms_dispatch_gate_open() is False

    def test_env_only_still_blocks(self) -> None:
        with (
            patch.dict("os.environ", {SMS_DISPATCH_ENABLED_ENV: "1"}),
            patch.object(sys, "argv", argv()),
        ):
            assert sms_dispatch_gate_open() is False

    def test_flag_only_still_blocks(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=False),
            patch.object(sys, "argv", argv(SMS_DISPATCH_ENABLED_FLAG)),
        ):
            assert sms_dispatch_gate_open() is False

    def test_both_flags_open_the_gate(self) -> None:
        with (
            patch.dict("os.environ", {SMS_DISPATCH_ENABLED_ENV: "1"}),
            patch.object(sys, "argv", argv(SMS_DISPATCH_ENABLED_FLAG)),
        ):
            assert sms_dispatch_gate_open() is True


class TestGuardIgnoresEnv(unittest.TestCase):
    """ENV(prod/dev/local)로 가르지 않는다 — Pilot이 ENV=dev로도 solapi를
    켤 수 있어서, env 값과 무관하게 같은 이중 게이트만 본다(KEY-284와
    같은 이유)."""

    def test_only_flag_combination_matters_regardless_of_env_value(self) -> None:
        with (
            patch.dict("os.environ", {SMS_DISPATCH_ENABLED_ENV: "1", "ENV": "dev"}),
            patch.object(sys, "argv", argv(SMS_DISPATCH_ENABLED_FLAG)),
        ):
            assert sms_dispatch_gate_open() is True

        with (
            patch.dict("os.environ", {SMS_DISPATCH_ENABLED_ENV: "1", "ENV": "prod"}),
            patch.object(sys, "argv", argv(SMS_DISPATCH_ENABLED_FLAG)),
        ):
            assert sms_dispatch_gate_open() is True


class TestClosedWorkerGate(unittest.IsolatedAsyncioTestCase):
    async def test_closed_gate_does_not_build_a_sender(self) -> None:
        from ai_worker.main import _run_message_dispatch_loop

        with (
            patch("ai_worker.main.Config", return_value=SimpleNamespace(SMS_PROVIDER=SmsProvider.SOLAPI)),
            patch("ai_worker.main.sms_dispatch_gate_open", return_value=False),
            patch("ai_worker.main.build_sms_sender") as build_sender,
            patch("ai_worker.main.dispatch_due_messages") as dispatch,
        ):
            await _run_message_dispatch_loop()

        build_sender.assert_not_called()
        dispatch.assert_not_called()
