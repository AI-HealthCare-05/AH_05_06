"""CLOVA OCR 어댑터 단위 테스트 — KEY-56.

httpx를 모킹해 외부 호출 없이 어댑터 계약을 검증한다.
성공·타임아웃·HTTP 오류·인식 실패·빈 응답·미지원 형식 경로를 다룬다.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ai_worker.adapters.clova import ClovaOcrError, ClovaOcrResult, call_clova_ocr

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20

_SUCCESS_BODY = {
    "version": "V2",
    "requestId": "test-req-id",
    "timestamp": 1234567890,
    "images": [
        {
            "inferResult": "SUCCESS",
            "message": "SUCCESS",
            "fields": [
                {"inferText": "CA-125 : 48 U/mL", "inferConfidence": 0.95},
                {"inferText": "AMH : 2.8 ng/mL", "inferConfidence": 0.92},
            ],
        }
    ],
}


def _make_mock_client(status_code: int, body: dict) -> AsyncMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = body

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


# ── 정상 경로 ─────────────────────────────────────────────────────────────────


async def test_success_returns_clova_ocr_result() -> None:
    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=_make_mock_client(200, _SUCCESS_BODY)):
        result = await call_clova_ocr(JPEG_BYTES, "image/jpeg")

    assert isinstance(result, ClovaOcrResult)
    assert "CA-125" in result.raw_text
    assert "AMH" in result.raw_text
    assert len(result.fields) == 2
    assert result.fields[0].text == "CA-125 : 48 U/mL"
    assert result.fields[0].confidence == pytest.approx(0.95)


async def test_png_format_is_accepted() -> None:
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=_make_mock_client(200, _SUCCESS_BODY)):
        result = await call_clova_ocr(png_bytes, "image/png")
    assert isinstance(result, ClovaOcrResult)


async def test_empty_fields_in_response_returns_empty_raw_text() -> None:
    body = {"images": [{"inferResult": "SUCCESS", "message": "SUCCESS", "fields": []}]}
    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=_make_mock_client(200, body)):
        result = await call_clova_ocr(JPEG_BYTES, "image/jpeg")
    assert result.raw_text == ""
    assert result.fields == []


# ── 외부 오류 표준화 ──────────────────────────────────────────────────────────


async def test_timeout_raises_clova_timeout_error() -> None:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = httpx.TimeoutException("timed out")

    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ClovaOcrError) as exc_info:
            await call_clova_ocr(JPEG_BYTES, "image/jpeg")

    assert exc_info.value.code == "CLOVA_TIMEOUT"


async def test_network_error_raises_clova_network_error() -> None:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ClovaOcrError) as exc_info:
            await call_clova_ocr(JPEG_BYTES, "image/jpeg")

    assert exc_info.value.code == "CLOVA_NETWORK_ERROR"


async def test_http_500_raises_clova_http_error() -> None:
    with patch(
        "ai_worker.adapters.clova.httpx.AsyncClient",
        return_value=_make_mock_client(500, {}),
    ):
        with pytest.raises(ClovaOcrError) as exc_info:
            await call_clova_ocr(JPEG_BYTES, "image/jpeg")

    assert exc_info.value.code == "CLOVA_HTTP_ERROR"


async def test_infer_failed_raises_clova_infer_failed() -> None:
    body = {"images": [{"inferResult": "FAILURE", "message": "인식 실패", "fields": []}]}
    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=_make_mock_client(200, body)):
        with pytest.raises(ClovaOcrError) as exc_info:
            await call_clova_ocr(JPEG_BYTES, "image/jpeg")

    assert exc_info.value.code == "CLOVA_INFER_FAILED"


async def test_empty_images_list_raises_parse_error() -> None:
    body: dict = {"images": []}
    with patch("ai_worker.adapters.clova.httpx.AsyncClient", return_value=_make_mock_client(200, body)):
        with pytest.raises(ClovaOcrError) as exc_info:
            await call_clova_ocr(JPEG_BYTES, "image/jpeg")

    assert exc_info.value.code == "CLOVA_PARSE_ERROR"


async def test_unsupported_mime_raises_without_http_call() -> None:
    with pytest.raises(ClovaOcrError) as exc_info:
        await call_clova_ocr(b"data", "text/plain")

    assert exc_info.value.code == "UNSUPPORTED_FORMAT"
