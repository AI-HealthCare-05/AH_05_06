"""문자 공급자 전환 어댑터 — KEY-248.

알리고에서 솔라피로 전환했다(팀 결정). 프로토콜(`SmsSender`)과 mock은 그대로
두고, 실제 어댑터만 `AligoSmsSender` → `SolapiSmsSender`로 통째로 바꿨다.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
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


def _solapi_authorization_header(api_key: str, api_secret: str) -> str:
    """HMAC-SHA256 서명 헤더값 — 솔라피 공식 SDK(solapi-python)의 방식과 같다.

    date + salt를 이어붙인 문자열을 api_secret으로 HMAC-SHA256 서명한다.
    salt는 요청마다 새로 만든다(재전송 방지) — 값 자체의 알고리즘은 서버가
    검증하지 않으므로, MAC 주소가 섞이는 uuid1 대신 secrets.token_hex를 쓴다.
    """
    date = datetime.now().astimezone().isoformat()
    salt = secrets.token_hex(16)
    signature = hmac.new(api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    return f"HMAC-SHA256 ApiKey={api_key}, Date={date}, salt={salt}, signature={signature}"


class SolapiSmsSender:
    """솔라피(SOLAPI) 문자 API의 단건 발송 어댑터.

    공급자 응답의 사람용 메시지는 반환하거나 예외에 복사하지 않는다. 솔라피가
    접수한 메시지 ID와 기계 판독용 상태 코드만 결과에 남긴다.

    단문(SMS)·장문(LMS) 분기는 솔라피의 자동판별(autoTypeDetect)에 맡기지
    않고, 이 코드베이스가 이미 쓰는 EUC-KR 90byte 셈(#183, message_templates.
    sms_bytes)을 그대로 따른다 — 인수조건 4번이 그 계산과 같은 결과를
    요구한다.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        sender_number: str,
        base_url: str = "https://api.solapi.com",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._sender_number = sender_number
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def send(self, to: str, body: str) -> SmsSendResult:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        headers = {
            "Authorization": _solapi_authorization_header(self._api_key, self._api_secret),
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [
                {
                    "to": to,
                    "from": self._sender_number,
                    "text": body,
                    "type": "SMS" if sms_bytes(body) <= SMS_LIMIT else "LMS",
                    # 솔라피 SDK의 기본값은 True다. 필드를 생략했을 때 서버가
                    # 명시한 type을 다시 판별하지 않도록 반드시 끈다.
                    "autoTypeDetect": False,
                }
            ]
        }
        try:
            response = await client.post(
                f"{self._base_url}/messages/v4/send-many/detail",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
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

        return _parse_send_result(result)


def _parse_send_result(result: object) -> SmsSendResult:
    if not isinstance(result, dict):
        raise SmsSendError("provider_invalid_response")

    failed = result.get("failedMessageList")
    if isinstance(failed, list) and failed:
        first_failed = failed[0]
        status_code = first_failed.get("statusCode") if isinstance(first_failed, dict) else None
        return SmsSendResult(
            status=SmsDeliveryStatus.FAILED,
            provider=SmsProvider.SOLAPI,
            provider_code=str(status_code) if status_code is not None else None,
        )

    sent = result.get("messageList")
    if not isinstance(sent, list) or not sent:
        raise SmsSendError("provider_invalid_response")
    first_sent = sent[0]
    if not isinstance(first_sent, dict):
        raise SmsSendError("provider_invalid_response")
    message_id = first_sent.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip():
        raise SmsSendError("provider_invalid_response")
    status_code = first_sent.get("statusCode")
    return SmsSendResult(
        status=SmsDeliveryStatus.SENT,
        provider=SmsProvider.SOLAPI,
        provider_message_id=message_id,
        provider_code=str(status_code) if status_code is not None else None,
    )


def build_sms_sender(settings: Config, *, client: httpx.AsyncClient | None = None) -> SmsSender:
    if settings.SMS_PROVIDER is SmsProvider.MOCK:
        return MockSmsSender()
    return SolapiSmsSender(
        api_key=settings.SOLAPI_API_KEY.get_secret_value(),
        api_secret=settings.SOLAPI_API_SECRET.get_secret_value(),
        sender_number=settings.SOLAPI_SENDER_NUMBER.get_secret_value(),
        base_url=settings.SOLAPI_BASE_URL,
        timeout_seconds=settings.SOLAPI_TIMEOUT_SECONDS,
        client=client,
    )
