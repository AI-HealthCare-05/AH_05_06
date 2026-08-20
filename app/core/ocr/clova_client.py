import base64
import time
import uuid

import httpx

from app.core.logger import setup_logger
from app.core.ocr.exceptions import OCRClientError, OCRServiceError, OCRTimeoutError, OCRUnsupportedFileTypeError
from app.core.ocr.schemas import ClovaOCRField, ClovaOCRImageResult

logger = setup_logger("ocr.clova")

# CLOVA OCR이 허용하는 파일 확장자 → CLOVA format 값
_FORMAT_MAP: dict[str, str] = {
    "jpg": "jpg",
    "jpeg": "jpg",
    "png": "png",
    "tif": "tiff",
    "tiff": "tiff",
    "pdf": "pdf",
    "bmp": "bmp",
}


class ClovaOCRClient:
    """NAVER CLOVA OCR General API 어댑터.

    외부 API 오류를 OCRError 계열로 변환해 호출자가 CLOVA 세부 사항을 몰라도 되게 한다.
    """

    def __init__(self, invoke_url: str, secret_key: str, timeout_seconds: int = 30) -> None:
        self._invoke_url = invoke_url
        self._secret_key = secret_key
        self._timeout = timeout_seconds

    async def run(self, image_bytes: bytes, filename: str) -> ClovaOCRImageResult:
        """파일 바이트를 CLOVA OCR에 전송하고 구조화된 결과를 반환한다.

        Args:
            image_bytes: 원본 파일 바이트.
            filename: 확장자 판단에 사용할 파일명.

        Returns:
            ClovaOCRImageResult — inferResult가 "SUCCESS"인 경우 fields에 텍스트가 담긴다.

        Raises:
            OCRUnsupportedFileTypeError: 확장자가 CLOVA OCR 지원 범위 밖인 경우.
            OCRTimeoutError: 타임아웃.
            OCRClientError: 4xx 오류.
            OCRServiceError: 5xx 오류.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        fmt = _FORMAT_MAP.get(ext)
        if not fmt:
            raise OCRUnsupportedFileTypeError(f"지원하지 않는 파일 형식: .{ext!r}")

        payload = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "images": [
                {
                    "format": fmt,
                    "name": filename,
                    "data": base64.b64encode(image_bytes).decode(),
                }
            ],
        }

        logger.debug("CLOVA OCR 요청: file=%s fmt=%s size=%d", filename, fmt, len(image_bytes))

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._invoke_url,
                    json=payload,
                    headers={"X-OCR-SECRET": self._secret_key},
                )
        except httpx.TimeoutException as exc:
            raise OCRTimeoutError("CLOVA OCR 요청 타임아웃") from exc
        except httpx.RequestError as exc:
            raise OCRClientError(f"CLOVA OCR 네트워크 오류: {exc}") from exc

        if resp.status_code >= 500:
            raise OCRServiceError(
                f"CLOVA OCR 서버 오류: {resp.status_code}",
                status_code=resp.status_code,
            )
        if not resp.is_success:
            raise OCRClientError(
                f"CLOVA OCR 오류: {resp.status_code}",
                status_code=resp.status_code,
            )

        body = resp.json()
        image_data = body["images"][0]

        fields = [
            ClovaOCRField(
                infer_text=f["inferText"],
                infer_confidence=f["inferConfidence"],
                line_break=f.get("lineBreak", False),
            )
            for f in image_data.get("fields", [])
        ]

        logger.debug(
            "CLOVA OCR 완료: file=%s result=%s fields=%d",
            filename,
            image_data["inferResult"],
            len(fields),
        )

        return ClovaOCRImageResult(
            uid=image_data["uid"],
            name=image_data["name"],
            infer_result=image_data["inferResult"],
            message=image_data.get("message", ""),
            fields=fields,
        )
