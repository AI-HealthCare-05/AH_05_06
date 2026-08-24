import base64
import hashlib
import hmac
import json
from typing import Any

from app.core.config import Config

# JWT와 같은 설정값을 입력으로 쓰더라도 HMAC 키는 용도별로 파생한다. 커서
# 서명을 JWT 서명에 그대로 재사용하면 한 기능의 키 사용 방식이 다른 기능까지
# 결합시킨다.
_CURSOR_SECRET = hmac.new(
    Config().SECRET_KEY.encode(),
    b"patient-visit-cursor-v1",
    hashlib.sha256,
).digest()


def encode_cursor(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(_CURSOR_SECRET, data, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(signature + data).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if cursor is None:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(cursor + padding)
        signature, data = decoded[:16], decoded[16:]
        expected = hmac.new(_CURSOR_SECRET, data, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error
