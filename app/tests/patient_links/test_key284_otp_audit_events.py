"""OTP 발급·발송·검증·잠금 감사 이벤트 — KEY-284, append-only."""

from unittest.mock import AsyncMock, patch

from tortoise.contrib.test import TestCase

from app.core.auth_errors import AuthError
from app.models.visits import PatientOtpChallenge, PatientOtpEvent, PatientOtpEventType
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


class TestAuditStorageFailurePolicy(TestCase):
    async def test_issue_stays_successful_after_the_sms_was_sent(self) -> None:
        await make_link()
        delivery = RecordingDelivery()
        service = PatientOtpService(delivery, secret_key=SECRET)

        with (
            patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)),
            patch(
                "app.services.patient_otp.PatientOtpEvent.create",
                new=AsyncMock(side_effect=RuntimeError("audit storage unavailable")),
            ),
        ):
            challenge = await service.issue(LINK_TOKEN)

        assert delivery.sent == [("01000009100", OTP)]
        assert challenge.patient_guide_link_id is not None
        assert await PatientOtpChallenge.all().count() == 1

    async def test_verify_stays_successful_after_the_otp_was_consumed(self) -> None:
        await make_link()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            await service.issue(LINK_TOKEN)

        with patch(
            "app.services.patient_otp.PatientOtpEvent.create",
            new=AsyncMock(side_effect=RuntimeError("audit storage unavailable")),
        ):
            verified_link = await service.verify(LINK_TOKEN, OTP)

        assert verified_link.patient_guide_link_id is not None
        challenge = await PatientOtpChallenge.get()
        assert challenge.consumed_at is not None

    async def test_audit_failure_does_not_replace_the_expected_otp_error(self) -> None:
        await make_link()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            await service.issue(LINK_TOKEN)

        wrong_code = "000000" if OTP != "000000" else "111111"
        with patch(
            "app.services.patient_otp.PatientOtpEvent.create",
            new=AsyncMock(side_effect=RuntimeError("audit storage unavailable")),
        ):
            try:
                await service.verify(LINK_TOKEN, wrong_code)
            except AuthError as exc:
                assert exc.code == "OTP_INVALID"
            else:
                raise AssertionError("잘못된 OTP가 허용되었습니다")


class TestEarlyExitPathsAreAlsoAudited(TestCase):
    """verify()의 조기 종료 4곳(미발급·이미 잠김·이미 사용·만료)도 감사에
    남는다 — iljun-sys 리뷰로 발견된 공백. 예전엔 이 네 경로가 함수 끝의
    _record_otp_event() 호출까지 못 가고 그 전에 raise돼서 한 줄도
    안 남았다.
    """

    async def test_verifying_a_never_issued_link_is_logged(self) -> None:
        link = await make_link()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)

        try:
            await service.verify(LINK_TOKEN, "000000")
        except AuthError as exc:
            assert exc.code == "OTP_NOT_ISSUED"
        else:
            raise AssertionError("발급된 적 없는데 검증이 통과했다")

        assert await _events(link.patient_guide_link_id) == [PatientOtpEventType.VERIFICATION_FAILED]

    async def test_verifying_an_already_used_otp_is_logged(self) -> None:
        link = await make_link()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            await service.issue(LINK_TOKEN)
        await service.verify(LINK_TOKEN, OTP)  # 정상 소비

        try:
            await service.verify(LINK_TOKEN, OTP)  # 재사용 시도
        except AuthError as exc:
            assert exc.code == "OTP_ALREADY_USED"
        else:
            raise AssertionError("이미 쓴 OTP가 다시 통과했다")

        events = await _events(link.patient_guide_link_id)
        assert events == [
            PatientOtpEventType.ISSUED,
            PatientOtpEventType.VERIFIED,
            PatientOtpEventType.VERIFICATION_FAILED,
        ]

    async def test_verifying_while_already_locked_is_logged_as_locked_again(self) -> None:
        link = await make_link()
        service = PatientOtpService(RecordingDelivery(), secret_key=SECRET)
        with patch("app.services.patient_otp.secrets.randbelow", return_value=int(OTP)):
            await service.issue(LINK_TOKEN)
        wrong = "000000" if OTP != "000000" else "111111"
        for _ in range(OTP_MAX_FAILURES):
            try:
                await service.verify(LINK_TOKEN, wrong)
            except AuthError:
                pass

        # 이미 잠긴 상태에서 한 번 더 시도 — 이것도 LOCKED로 남아야 한다.
        try:
            await service.verify(LINK_TOKEN, wrong)
        except AuthError as exc:
            assert exc.code == "OTP_LOCKED"
        else:
            raise AssertionError("잠긴 상태인데 검증이 통과했다")

        events = await _events(link.patient_guide_link_id)
        assert events[-1] is PatientOtpEventType.LOCKED
        # 처음 잠긴 순간 1건 + 잠긴 채로 또 시도한 것 1건, 최소 두 번은 LOCKED다.
        assert events.count(PatientOtpEventType.LOCKED) >= 2
