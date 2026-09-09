"""SolapiOtpDelivery·ApprovedPhonesOnlyDelivery — KEY-284."""

import pytest

from app.core.auth_errors import AuthError as ApiError
from app.services.message_templates import SYSTEM_BODY
from app.services.patient_otp import ApprovedPhonesOnlyDelivery, SolapiOtpDelivery
from app.services.sms_sender import SmsDeliveryStatus, SmsProvider, SmsSendResult

PHONE = "01000009284"
CODE = "042731"
HOSPITAL_NAME = "합성의원"


class _FixedResultSender:
    def __init__(self, result: SmsSendResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def send(self, to: str, body: str) -> SmsSendResult:
        self.calls.append((to, body))
        return self.result


async def test_sends_the_system_body_template_and_succeeds_on_sent() -> None:
    """실제 발송 문구는 message_templates.SYSTEM_BODY 하나다 — 스탭이 문구
    관리 화면에서 보는 문구와 실제로 나가는 문구가 다르면 안 된다
    (iljun-sys 리뷰로 발견된 불일치).
    """
    sender = _FixedResultSender(
        SmsSendResult(status=SmsDeliveryStatus.SENT, provider=SmsProvider.SOLAPI, provider_message_id="msg-1")
    )
    delivery = SolapiOtpDelivery(sender)

    await delivery.send(PHONE, CODE, HOSPITAL_NAME)

    assert sender.calls == [(PHONE, SYSTEM_BODY.format(의원명=HOSPITAL_NAME, 번호=CODE))]
    assert HOSPITAL_NAME in sender.calls[0][1]
    # 문구에 링크·진료정보가 없다 — 인증번호와 유효시간 안내만 있다.
    assert "http" not in sender.calls[0][1]
    assert "3분" in sender.calls[0][1]


@pytest.mark.parametrize("status", [SmsDeliveryStatus.FAILED, SmsDeliveryStatus.PENDING])
async def test_raises_when_not_confirmed_sent(status: SmsDeliveryStatus) -> None:
    sender = _FixedResultSender(SmsSendResult(status=status, provider=SmsProvider.SOLAPI))
    delivery = SolapiOtpDelivery(sender)

    with pytest.raises(RuntimeError):
        await delivery.send(PHONE, CODE, HOSPITAL_NAME)


async def test_approved_phones_only_forwards_to_the_wrapped_delivery() -> None:
    sender = _FixedResultSender(SmsSendResult(status=SmsDeliveryStatus.SENT, provider=SmsProvider.SOLAPI))
    inner = SolapiOtpDelivery(sender)
    delivery = ApprovedPhonesOnlyDelivery(inner, frozenset({PHONE}))

    await delivery.send(PHONE, CODE, HOSPITAL_NAME)

    assert len(sender.calls) == 1
    assert HOSPITAL_NAME in sender.calls[0][1]


async def test_approved_phones_only_blocks_unlisted_numbers_without_calling_the_sender() -> None:
    sender = _FixedResultSender(SmsSendResult(status=SmsDeliveryStatus.SENT, provider=SmsProvider.SOLAPI))
    inner = SolapiOtpDelivery(sender)
    delivery = ApprovedPhonesOnlyDelivery(inner, frozenset({"01099999999"}))

    with pytest.raises(ApiError) as caught:
        await delivery.send(PHONE, CODE, HOSPITAL_NAME)

    assert caught.value.code == "OTP_DELIVERY_UNAVAILABLE"
    assert sender.calls == []
    # 막힌 이유·번호가 예외에 그대로 실리지 않는다.
    assert PHONE not in str(caught.value)
