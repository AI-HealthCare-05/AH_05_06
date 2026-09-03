"""문자 공급자 전환 어댑터 — KEY-248."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import httpx

from app.core.config import Config, SmsProvider
from app.services.message_templates import SMS_LIMIT, sms_bytes


class SmsDeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    PENDING = "pending"


@dataclass(frozen=True)
class SmsSendResult:
    status: SmsDeliveryStatus
    provider: SmsProvider
    provider_message_id: str | None = None
    provider_code: str | None = None


class SmsSender(Protocol):
    async def send(self, to: str, body: str) -> SmsSendResult: ...


class SmsSendError(RuntimeError):
    """공급자 응답 원문과 전화번호를 상위 예외로 전달하지 않는다."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("sms provider request failed")


class MockSmsSender:
    """외부 호출 없이 주입한 결과를 그대로 반환하는 결정적 발송기."""

    def __init__(
        self,
        status: SmsDeliveryStatus = SmsDeliveryStatus.SENT,
        *,
        provider_message_id: str = "mock-message-1",
    ) -> None:
        self._result = SmsSendResult(
            status=status,
            provider=SmsProvider.MOCK,
            provider_message_id=provider_message_id if status is not SmsDeliveryStatus.FAILED else None,
        )

    async def send(self, to: str, body: str) -> SmsSendResult:
        return self._result


class AligoSmsSender:
    """알리고 문자 API의 단건 발송 어댑터.

    공급자 응답의 사람용 메시지는 반환하거나 예외에 복사하지 않는다. 알리고가
    접수한 메시지 ID와 기계 판독용 결과 코드만 결과에 남긴다.
    """

    def __init__(
        self,
        *,
        api_key: str,
        user_id: str,
        sender_number: str,
        base_url: str = "https://apis.aligo.in",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._user_id = user_id
        self._sender_number = sender_number
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def send(self, to: str, body: str) -> SmsSendResult:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/send/",
                data={
                    "key": self._api_key,
                    "user_id": self._user_id,
                    "sender": self._sender_number,
                    "receiver": to,
                    "msg": body,
                    "msg_type": "SMS" if sms_bytes(body) <= SMS_LIMIT else "LMS",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException:
            raise SmsSendError("provider_timeout") from None
        except httpx.HTTPStatusError as exc:
            raise SmsSendError(f"provider_http_{exc.response.status_code}") from None
        except httpx.HTTPError:
            raise SmsSendError("provider_transport_error") from None
        except (TypeError, ValueError):
            raise SmsSendError("provider_invalid_response") from None
        finally:
            if owns_client:
                await client.aclose()

        if not isinstance(payload, dict):
            raise SmsSendError("provider_invalid_response")
        result_code = _provider_code(payload.get("result_code"))
        if result_code is None:
            raise SmsSendError("provider_invalid_response")
        if result_code < 0:
            return SmsSendResult(
                status=SmsDeliveryStatus.FAILED,
                provider=SmsProvider.ALIGO,
                provider_code=str(result_code),
            )
        message_id = payload.get("msg_id")
        if not isinstance(message_id, (str, int)) or not str(message_id).strip():
            raise SmsSendError("provider_invalid_response")
        return SmsSendResult(
            status=SmsDeliveryStatus.SENT,
            provider=SmsProvider.ALIGO,
            provider_message_id=str(message_id),
            provider_code=str(result_code),
        )


def build_sms_sender(settings: Config, *, client: httpx.AsyncClient | None = None) -> SmsSender:
    if settings.SMS_PROVIDER is SmsProvider.MOCK:
        return MockSmsSender()
    return AligoSmsSender(
        api_key=settings.ALIGO_KEY.get_secret_value(),
        user_id=settings.ALIGO_USER_ID.get_secret_value(),
        sender_number=settings.ALIGO_SENDER_NUMBER.get_secret_value(),
        base_url=settings.ALIGO_BASE_URL,
        timeout_seconds=settings.ALIGO_TIMEOUT_SECONDS,
        client=client,
    )


def _provider_code(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
