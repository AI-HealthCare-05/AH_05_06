"""OTP 발급·발송·검증·잠금 감사 이벤트 — KEY-284, append-only."""

from unittest.mock import patch

from tortoise.contrib.test import TestCase

from app.models.visits import PatientOtpEvent, PatientOtpEventType
from app.services.patient_otp import OTP_MAX_FAILURES, PatientOtpService
from app.tests.patient_links.test_patient_otp import (
    LINK_TOKEN,
    OTP,
    SECRET,
    FailingDelivery,
    RecordingDelivery,
    make_link,
)


async def _events(link_id: int) -> list[PatientOtpEventType]:
    rows = await PatientOtpEvent.filter(patient_guide_link_id=link_id).order_by("patient_otp_event_id").all()
    return [row.event_type for row in rows]


class TestIssueLogsEvents(TestCase):
    async def test_a_successful_issue_logs_issued(self) -> None:
        link = await make_link()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)

        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            await service.issue(LINK_TOKEN)

        assert await _events(link.patient_guide_link_id) == [PatientOtpEventType.ISSUED]

    async def test_a_failed_delivery_logs_delivery_failed_not_issued(self) -> None:
        link = await make_link()
        service = PatientOtpService(FailingDelivery(), secret_key=SECRET)

        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            try:
                await service.issue(LINK_TOKEN)
                raise AssertionError("발송 실패인데 issue()가 성공했다")
            except Exception:
                pass

        assert await _events(link.patient_guide_link_id) == [PatientOtpEventType.DELIVERY_FAILED]


class TestVerifyLogsEvents(TestCase):
    async def _issue(self) -> None:
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            await service.issue(LINK_TOKEN)

    async def test_a_correct_code_logs_verified(self) -> None:
        link = await make_link()
        await self._issue()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)

        await service.verify(LINK_TOKEN, OTP)

        assert await _events(link.patient_guide_link_id) == [
            PatientOtpEventType.ISSUED,
            PatientOtpEventType.VERIFIED,
        ]

    async def test_a_wrong_code_logs_verification_failed(self) -> None:
        link = await make_link()
        await self._issue()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)

        try:
            await service.verify(LINK_TOKEN, "000000" if OTP != "000000" else "111111")
        except Exception:
            pass

        assert await _events(link.patient_guide_link_id) == [
            PatientOtpEventType.ISSUED,
            PatientOtpEventType.VERIFICATION_FAILED,
        ]

    async def test_reaching_max_failures_logs_locked_not_verification_failed(self) -> None:
        link = await make_link()
        await self._issue()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)
        wrong = "000000" if OTP != "000000" else "111111"

        for _ in range(OTP_MAX_FAILURES):
            try:
                await service.verify(LINK_TOKEN, wrong)
            except Exception:
                pass

        events = await _events(link.patient_guide_link_id)
        assert events[0] is PatientOtpEventType.ISSUED
        assert events[1:-1] == [PatientOtpEventType.VERIFICATION_FAILED] * (OTP_MAX_FAILURES - 1)
        assert events[-1] is PatientOtpEventType.LOCKED


class TestEventsNeverCarrySensitiveValues(TestCase):
    async def test_event_rows_have_no_phone_or_otp_fields_at_all(self) -> None:
        """모델 자체에 그런 필드가 없다 — 구조적으로 담을 수 없다."""
        field_names = set(PatientOtpEvent._meta.fields_map.keys())
        assert "phone" not in field_names
        assert "otp_digest" not in field_names
        assert "otp_salt" not in field_names
        assert "code" not in field_names
