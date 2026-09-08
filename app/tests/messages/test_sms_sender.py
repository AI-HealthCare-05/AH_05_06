"""문자 공급자 어댑터 — KEY-248 (알리고 → 솔라피 전환)."""

import hashlib
import hmac
import json
from datetime import datetime

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Config, SmsProvider
from app.services.sms_sender import (
    MockSmsSender,
    SmsDeliveryStatus,
    SmsSendError,
    SolapiSmsSender,
    build_sms_sender,
)

API_KEY = "synthetic-solapi-key"
API_SECRET = "synthetic-solapi-secret"
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


def _parse_authorization(header: str) -> dict[str, str]:
    scheme, _, rest = header.partition(" ")
    assert scheme == "HMAC-SHA256"
    parts = dict(item.strip().split("=", 1) for item in rest.split(","))
    return parts


async def test_solapi_signs_requests_with_hmac_sha256() -> None:
    """factory 배선부터 URL·헤더·본문까지 공급자 계약을 문자 그대로 잠근다."""
    captured: dict[str, object] = {}
    sent_text = "합성 안내 본문"
    before = datetime.now().astimezone()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"messageList": [{"messageId": "msg-1", "statusCode": "2000"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = build_sms_sender(
            settings(
                SMS_PROVIDER=SmsProvider.SOLAPI,
                SOLAPI_API_KEY=SecretStr(API_KEY),
                SOLAPI_API_SECRET=SecretStr(API_SECRET),
                SOLAPI_SENDER_NUMBER=SecretStr(SENDER),
                SOLAPI_BASE_URL="https://gateway.example",
            ),
            client=client,
        )
        await sender.send(RECEIVER, sent_text)

    after = datetime.now().astimezone()
    assert captured["url"] == "https://gateway.example/messages/v4/send-many/detail"
    assert isinstance(captured["authorization"], str)
    parts = _parse_authorization(captured["authorization"])
    assert set(parts) == {"apiKey", "date", "salt", "signature"}
    assert parts["apiKey"] == API_KEY
    signed_at = datetime.fromisoformat(parts["date"])
    assert before <= signed_at <= after
    expected_signature = hmac.new(
        API_SECRET.encode(), (parts["date"] + parts["salt"]).encode(), hashlib.sha256
    ).hexdigest()
    assert parts["signature"] == expected_signature

    assert captured["body"] == {
        "messages": [
            {
                "to": RECEIVER,
                "from": SENDER,
                "text": sent_text,
                "type": "SMS",
                "autoTypeDetect": False,
            }
        ]
    }


async def test_solapi_uses_a_fresh_salt_for_each_request() -> None:
    authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorizations.append(request.headers["Authorization"])
        return httpx.Response(200, json={"messageList": [{"messageId": "msg-1", "statusCode": "2000"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = SolapiSmsSender(api_key=API_KEY, api_secret=API_SECRET, sender_number=SENDER, client=client)
        await sender.send(RECEIVER, "첫 요청")
        await sender.send(RECEIVER, "두 번째 요청")

    first = _parse_authorization(authorizations[0])
    second = _parse_authorization(authorizations[1])
    assert first["salt"] != second["salt"]


async def test_solapi_uses_the_existing_euc_kr_90_byte_boundary() -> None:
    message_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert len(body["messages"]) == 1
        message = body["messages"][0]
        message_types.append(message["type"])
        assert message["autoTypeDetect"] is False
        assert message["to"] == RECEIVER
        assert message["from"] == SENDER
        return httpx.Response(
            200,
            json={"messageList": [{"messageId": str(len(message_types)), "statusCode": "2000"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = SolapiSmsSender(api_key=API_KEY, api_secret=API_SECRET, sender_number=SENDER, client=client)
        short = await sender.send(RECEIVER, "a" * 90)
        long = await sender.send(RECEIVER, "a" * 91)

    assert message_types == ["SMS", "LMS"]
    assert short.provider_message_id == "1"
    assert long.provider_message_id == "2"


async def test_solapi_rejection_does_not_expose_provider_message_or_numbers() -> None:
    leaked = f"key={API_SECRET} sender={SENDER} receiver={RECEIVER}"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "messageList": [],
                "failedMessageList": [
                    {
                        "to": RECEIVER,
                        "from": SENDER,
                        "type": "SMS",
                        "statusMessage": leaked,
                        "statusCode": "3993",
                        "messageId": "failed-1",
                        "accountId": "synthetic-account",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SolapiSmsSender(
            api_key=API_KEY,
            api_secret=API_SECRET,
            sender_number=SENDER,
            client=client,
        ).send(RECEIVER, "합성 안내")

    rendered = repr(result)
    assert result.status is SmsDeliveryStatus.FAILED
    assert result.provider_code == "3993"
    assert API_SECRET not in rendered
    assert SENDER not in rendered
    assert RECEIVER not in rendered
    assert leaked not in rendered


async def test_transport_error_is_sanitized_and_has_no_chained_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"{API_SECRET} {SENDER} {RECEIVER}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = SolapiSmsSender(
            api_key=API_KEY,
            api_secret=API_SECRET,
            sender_number=SENDER,
            client=client,
        )
        with pytest.raises(SmsSendError) as caught:
            await sender.send(RECEIVER, "합성 안내")

    assert caught.value.reason == "provider_transport_error"
    assert caught.value.__cause__ is None
    assert str(caught.value) == "sms provider request failed"
    assert API_SECRET not in str(caught.value)
    assert SENDER not in str(caught.value)
    assert RECEIVER not in str(caught.value)


@pytest.mark.parametrize(
    "missing_name",
    [
        "SOLAPI_API_KEY",
        "SOLAPI_API_SECRET",
        "SOLAPI_SENDER_NUMBER",
    ],
)
def test_solapi_requires_every_credential_without_printing_values(missing_name: str) -> None:
    credentials = {
        "SOLAPI_API_KEY": SecretStr(API_KEY),
        "SOLAPI_API_SECRET": SecretStr(API_SECRET),
        "SOLAPI_SENDER_NUMBER": SecretStr(SENDER),
    }
    credentials[missing_name] = SecretStr("")

    with pytest.raises(ValidationError) as caught:
        settings(
            SMS_PROVIDER=SmsProvider.SOLAPI,
            **credentials,
        )

    rendered = str(caught.value)
    assert missing_name in rendered
    assert API_KEY not in rendered
    assert API_SECRET not in rendered
    assert SENDER not in rendered


@pytest.mark.parametrize("message_id", [12345, "msg-12345"])
async def test_solapi_accepts_string_and_integer_message_ids(message_id: int | str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messageList": [{"messageId": message_id, "statusCode": "2000"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SolapiSmsSender(
            api_key=API_KEY,
            api_secret=API_SECRET,
            sender_number=SENDER,
            client=client,
        ).send(RECEIVER, "합성 안내")

    assert result.provider_message_id == str(message_id)


@pytest.mark.parametrize(
    "response_body",
    [
        [],
        {},
        {"messageList": []},
        {"messageList": [{}]},
        {"messageList": [{"messageId": True}]},
    ],
)
async def test_solapi_rejects_invalid_provider_responses(response_body: object) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = SolapiSmsSender(api_key=API_KEY, api_secret=API_SECRET, sender_number=SENDER, client=client)
        with pytest.raises(SmsSendError) as caught:
            await sender.send(RECEIVER, "합성 안내")

    assert caught.value.reason == "provider_invalid_response"


def test_solapi_factory_keeps_credentials_out_of_repr() -> None:
    sender = build_sms_sender(
        settings(
            SMS_PROVIDER=SmsProvider.SOLAPI,
            SOLAPI_API_KEY=SecretStr(API_KEY),
            SOLAPI_API_SECRET=SecretStr(API_SECRET),
            SOLAPI_SENDER_NUMBER=SecretStr(SENDER),
        )
    )

    rendered = repr(sender)
    assert isinstance(sender, SolapiSmsSender)
    assert API_KEY not in rendered
    assert API_SECRET not in rendered
    assert SENDER not in rendered
