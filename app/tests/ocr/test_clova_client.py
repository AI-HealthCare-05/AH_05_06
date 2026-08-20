"""[KEY-56] CLOVA OCR 클라이언트 단위 테스트.

실제 CLOVA API를 호출하지 않고 httpx를 모킹해 어댑터 로직만 검증한다.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.ocr.clova_client import ClovaOCRClient
from app.core.ocr.exceptions import OCRClientError, OCRServiceError, OCRTimeoutError, OCRUnsupportedFileTypeError
from app.core.ocr.schemas import ClovaOCRImageResult

_CLIENT = ClovaOCRClient(
    invoke_url="https://ocr.example.com/general",
    secret_key="test-secret",
)
_SAMPLE_BYTES = b"fake-image-bytes"


def _make_clova_response(infer_result: str = "SUCCESS", fields: list | None = None) -> dict:
    return {
        "version": "V2",
        "requestId": "test-request-id",
        "timestamp": 1000000,
        "images": [
            {
                "uid": "test-uid",
                "name": "test.jpg",
                "inferResult": infer_result,
                "message": infer_result,
                "fields": fields
                or [
                    {"inferText": "진단명:", "inferConfidence": 0.99, "lineBreak": False},
                    {"inferText": "자궁내막증", "inferConfidence": 0.97, "lineBreak": True},
                    {"inferText": "내원 사유:", "inferConfidence": 0.98, "lineBreak": False},
                    {"inferText": "골반 통증", "inferConfidence": 0.95, "lineBreak": True},
                ],
            }
        ],
    }


def _mock_response(status_code: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = body or {}
    resp.text = json.dumps(body or {})
    return resp


@pytest.mark.asyncio
async def test_run_success() -> None:
    mock_resp = _mock_response(200, _make_clova_response())

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await _CLIENT.run(_SAMPLE_BYTES, "test.jpg")

    assert isinstance(result, ClovaOCRImageResult)
    assert result.infer_result == "SUCCESS"
    assert len(result.fields) == 4
    assert "진단명:" in result.raw_text
    assert "자궁내막증" in result.raw_text


@pytest.mark.asyncio
async def test_raw_text_line_breaks() -> None:
    fields = [
        {"inferText": "A", "inferConfidence": 0.9, "lineBreak": True},
        {"inferText": "B", "inferConfidence": 0.9, "lineBreak": False},
        {"inferText": "C", "inferConfidence": 0.9, "lineBreak": True},
    ]
    mock_resp = _mock_response(200, _make_clova_response(fields=fields))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await _CLIENT.run(_SAMPLE_BYTES, "test.png")

    assert result.raw_text == "A\nB C"


@pytest.mark.asyncio
async def test_unsupported_file_type() -> None:
    with pytest.raises(OCRUnsupportedFileTypeError) as exc_info:
        await _CLIENT.run(_SAMPLE_BYTES, "document.docx")
    assert exc_info.value.code == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_timeout_raises_ocr_timeout_error() -> None:
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(OCRTimeoutError) as exc_info:
            await _CLIENT.run(_SAMPLE_BYTES, "test.jpg")
    assert exc_info.value.code == "OCR_TIMEOUT"


@pytest.mark.asyncio
async def test_server_error_raises_ocr_service_error() -> None:
    mock_resp = _mock_response(503)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(OCRServiceError) as exc_info:
            await _CLIENT.run(_SAMPLE_BYTES, "test.jpg")
    assert exc_info.value.code == "OCR_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_client_error_raises_ocr_client_error() -> None:
    mock_resp = _mock_response(401)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(OCRClientError) as exc_info:
            await _CLIENT.run(_SAMPLE_BYTES, "test.jpg")
    assert exc_info.value.code == "OCR_CLIENT_ERROR"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_network_error_raises_ocr_client_error() -> None:
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(OCRClientError) as exc_info:
            await _CLIENT.run(_SAMPLE_BYTES, "test.jpg")
    assert exc_info.value.code == "OCR_CLIENT_ERROR"


@pytest.mark.parametrize(
    "filename",
    ["test.jpg", "test.jpeg", "test.png", "test.pdf", "test.tiff", "test.tif", "test.bmp"],
)
@pytest.mark.asyncio
async def test_supported_extensions(filename: str) -> None:
    mock_resp = _mock_response(200, _make_clova_response(fields=[]))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await _CLIENT.run(_SAMPLE_BYTES, filename)
    assert result.infer_result == "SUCCESS"
