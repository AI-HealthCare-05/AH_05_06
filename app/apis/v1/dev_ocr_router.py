"""[KEY-56] OCR 클라이언트 임시 테스트 엔드포인트.

ENV != prod 일 때만 라우터에 등록된다.
실제 문서 업로드·OCR 연동(KEY-39, KEY-40)이 완료되면 이 파일을 삭제한다.
"""

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core import config
from app.core.ocr import (
    ClovaOCRClient,
    classify_by_filename,
    is_supported_mime,
)
from app.core.ocr.exceptions import OCRError

dev_ocr_router = APIRouter(prefix="/dev", tags=["dev-ocr"])

_MAX_BYTES = 20 * 1024 * 1024  # 20 MB — upload.js와 동일


class OcrTestResponse(BaseModel):
    filename: str
    mime_type: str
    document_type: str
    classified_by: str
    ocr_available: bool
    ocr_status: str | None = None
    raw_text: str | None = None
    notice: str | None = None


def _get_clova_client() -> ClovaOCRClient | None:
    if not config.CLOVA_OCR_INVOKE_URL:
        return None
    return ClovaOCRClient(
        invoke_url=config.CLOVA_OCR_INVOKE_URL,
        secret_key=config.CLOVA_OCR_SECRET_KEY,
        timeout_seconds=config.CLOVA_OCR_TIMEOUT_SECONDS,
    )


@dev_ocr_router.post(
    "/ocr-test",
    response_model=OcrTestResponse,
    status_code=status.HTTP_200_OK,
    summary="[임시] OCR 분류·추출 테스트",
    description=(
        "파일을 업로드하면 문서 유형을 자동 분류하고 "
        "CLOVA_OCR_INVOKE_URL이 설정된 경우 OCR 텍스트도 반환합니다. "
        "이 엔드포인트는 dev/local 환경에서만 활성화됩니다."
    ),
)
async def ocr_test(file: UploadFile) -> OcrTestResponse:
    mime = file.content_type or ""
    filename = file.filename or "unknown"

    if not is_supported_mime(mime):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UNSUPPORTED_FILE_TYPE", "detail": f"지원하지 않는 파일 형식: {mime}"},
        )

    image_bytes = await file.read()
    if len(image_bytes) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_TOO_LARGE", "detail": "파일이 20 MB를 초과합니다."},
        )

    classification = classify_by_filename(filename, mime)

    client = _get_clova_client()
    if client is None:
        return OcrTestResponse(
            filename=filename,
            mime_type=mime,
            document_type=classification.document_type,
            classified_by=classification.classified_by,
            ocr_available=False,
            notice="CLOVA_OCR_INVOKE_URL이 설정되지 않았습니다. 분류 결과만 반환합니다.",
        )

    try:
        result = await client.run(image_bytes, filename)
    except OCRError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "detail": exc.message},
        ) from exc

    return OcrTestResponse(
        filename=filename,
        mime_type=mime,
        document_type=classification.document_type,
        classified_by=classification.classified_by,
        ocr_available=True,
        ocr_status=result.infer_result,
        raw_text=result.raw_text or None,
    )
