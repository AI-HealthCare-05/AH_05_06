"""SolapiOtpDelivery·ApprovedPhonesOnlyDelivery — KEY-284."""

import pytest

from app.core.auth_errors import AuthError as ApiError
from app.services.patient_otp import OTP_MESSAGE_TEMPLATE, ApprovedPhonesOnlyDelivery, SolapiOtpDelivery
from app.services.sms_sender import SmsDeliveryStatus, SmsProvider, SmsSendResult

PHONE = "01000009284"
CODE = "042731"


class _FixedResultSender:
    def __init__(self, result: SmsSendResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def send(self, to: str, body: str) -> SmsSendResult:
        self.calls.append((to, body))
        return self.result


async def test_sends_the_otp_template_and_succeeds_on_sent() -> None:
    sender = _FixedResultSender(
        SmsSendResult(status=SmsDeliveryStatus.SENT, provider=SmsProvider.SOLAPI, provider_message_id="msg-1")
    )
    delivery = SolapiOtpDelivery(sender)

    await delivery.send(PHONE, CODE)

    assert sender.calls == [(PHONE, OTP_MESSAGE_TEMPLATE.format(code=CODE))]
    # 문구에 링크·진료정보가 없다 — 인증번호와 유효시간 안내만 있다.
    assert "http" not in sender.calls[0][1]
    assert "3분" in sender.calls[0][1]


@pytest.mark.parametrize("status", [SmsDeliveryStatus.FAILED, SmsDeliveryStatus.PENDING])
async def test_raises_when_not_confirmed_sent(status: SmsDeliveryStatus) -> None:
    sender = _FixedResultSender(SmsSendResult(status=status, provider=SmsProvider.SOLAPI))
    delivery = SolapiOtpDelivery(sender)

    with pytest.raises(RuntimeError):
        await delivery.send(PHONE, CODE)


async def test_approved_phones_only_forwards_to_the_wrapped_delivery() -> None:
    sender = _FixedResultSender(SmsSendResult(status=SmsDeliveryStatus.SENT, provider=SmsProvider.SOLAPI))
    inner = SolapiOtpDelivery(sender)
    delivery = ApprovedPhonesOnlyDelivery(inner, frozenset({PHONE}))

    await delivery.send(PHONE, CODE)

    assert len(sender.calls) == 1


async def test_approved_phones_only_blocks_unlisted_numbers_without_calling_the_sender() -> None:
    sender = _FixedResultSender(SmsSendResult(status=SmsDeliveryStatus.SENT, provider=SmsProvider.SOLAPI))
    inner = SolapiOtpDelivery(sender)
    delivery = ApprovedPhonesOnlyDelivery(inner, frozenset({"01099999999"}))

    with pytest.raises(ApiError) as caught:
        await delivery.send(PHONE, CODE)

    assert caught.value.code == "OTP_DELIVERY_UNAVAILABLE"
    assert sender.calls == []
    # 막힌 이유·번호가 예외에 그대로 실리지 않는다.
    assert PHONE not in str(caught.value)
