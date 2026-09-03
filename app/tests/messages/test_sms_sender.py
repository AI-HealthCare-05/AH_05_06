"""문자 공급자 어댑터 — KEY-248."""

from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Config, SmsProvider
from app.services.sms_sender import (
    AligoSmsSender,
    MockSmsSender,
    SmsDeliveryStatus,
    SmsSendError,
    build_sms_sender,
)

API_KEY = "synthetic-aligo-key"
USER_ID = "synthetic-user"
SENDER = "0200000000"
RECEIVER = "01000000000"


def settings(**values: object) -> Config:
    return Config(DB_PASSWORD="synthetic-db-password", **values)  # type: ignore[arg-type]


async def test_mock_is_the_default_and_needs_no_credentials() -> None:
    sender = build_sms_sender(settings())

    result = await sender.send(RECEIVER, "합성 안내")

    assert isinstance(sender, MockSmsSender)
    assert result.status is SmsDeliveryStatus.SENT
    assert result.provider is SmsProvider.MOCK
    assert result.provider_message_id == "mock-message-1"


@pytest.mark.parametrize(
    "status",
    [SmsDeliveryStatus.SENT, SmsDeliveryStatus.FAILED, SmsDeliveryStatus.PENDING],
)
async def test_mock_scenarios_are_injected_deterministically(status: SmsDeliveryStatus) -> None:
    sender = MockSmsSender(status, provider_message_id="mock-fixed")

    first = await sender.send(RECEIVER, "첫 요청")
    second = await sender.send("01099999999", "다른 요청")

    assert first == second
    assert first.status is status
    assert first.provider_message_id == (None if status is SmsDeliveryStatus.FAILED else "mock-fixed")


async def test_aligo_uses_the_existing_euc_kr_90_byte_boundary() -> None:
    message_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        message_types.append(form["msg_type"][0])
        assert form["key"] == [API_KEY]
        assert form["user_id"] == [USER_ID]
        assert form["sender"] == [SENDER]
        assert form["receiver"] == [RECEIVER]
        return httpx.Response(200, json={"result_code": "1", "message": "success", "msg_id": len(message_types)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = AligoSmsSender(
            api_key=API_KEY,
            user_id=USER_ID,
            sender_number=SENDER,
            client=client,
        )
        short = await sender.send(RECEIVER, "a" * 90)
        long = await sender.send(RECEIVER, "a" * 91)

    assert message_types == ["SMS", "LMS"]
    assert short.provider_message_id == "1"
    assert long.provider_message_id == "2"


async def test_aligo_rejection_does_not_expose_provider_message_or_numbers() -> None:
    leaked = f"key={API_KEY} sender={SENDER} receiver={RECEIVER}"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result_code": "-101", "message": leaked})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AligoSmsSender(
            api_key=API_KEY,
            user_id=USER_ID,
            sender_number=SENDER,
            client=client,
        ).send(RECEIVER, "합성 안내")

    rendered = repr(result)
    assert result.status is SmsDeliveryStatus.FAILED
    assert result.provider_code == "-101"
    assert API_KEY not in rendered
    assert SENDER not in rendered
    assert RECEIVER not in rendered
    assert leaked not in rendered


async def test_transport_error_is_sanitized_and_has_no_chained_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"{API_KEY} {SENDER} {RECEIVER}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = AligoSmsSender(
            api_key=API_KEY,
            user_id=USER_ID,
            sender_number=SENDER,
            client=client,
        )
        with pytest.raises(SmsSendError) as caught:
            await sender.send(RECEIVER, "합성 안내")

    assert caught.value.reason == "provider_transport_error"
    assert caught.value.__cause__ is None
    assert str(caught.value) == "sms provider request failed"
    assert API_KEY not in str(caught.value)
    assert SENDER not in str(caught.value)
    assert RECEIVER not in str(caught.value)


def test_aligo_requires_all_credentials_without_printing_values() -> None:
    with pytest.raises(ValidationError) as caught:
        settings(
            SMS_PROVIDER=SmsProvider.ALIGO,
            ALIGO_KEY=SecretStr(API_KEY),
            ALIGO_USER_ID=SecretStr(USER_ID),
            ALIGO_SENDER_NUMBER=SecretStr(""),
        )

    rendered = str(caught.value)
    assert "ALIGO_SENDER_NUMBER" in rendered
    assert API_KEY not in rendered
    assert USER_ID not in rendered


def test_aligo_factory_keeps_credentials_out_of_repr() -> None:
    sender = build_sms_sender(
        settings(
            SMS_PROVIDER=SmsProvider.ALIGO,
            ALIGO_KEY=SecretStr(API_KEY),
            ALIGO_USER_ID=SecretStr(USER_ID),
            ALIGO_SENDER_NUMBER=SecretStr(SENDER),
        )
    )

    rendered = repr(sender)
    assert isinstance(sender, AligoSmsSender)
    assert API_KEY not in rendered
    assert USER_ID not in rendered
    assert SENDER not in rendered
