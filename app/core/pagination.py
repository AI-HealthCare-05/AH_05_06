import base64
import hashlib
import hmac
import json
from typing import Any

from app.core.config import Config

_CURSOR_SECRET = Config().SECRET_KEY.encode()


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
