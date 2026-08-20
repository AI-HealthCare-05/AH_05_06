class OCRError(Exception):
    """OCR 오류 기반 클래스. code 는 API 응답의 code 필드에 그대로 쓴다."""

    code: str = "OCR_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class OCRUnsupportedFileTypeError(OCRError):
    """지원하지 않는 파일 형식 — 업로드 단계에서 차단한다."""

    code = "UNSUPPORTED_FILE_TYPE"


class OCRInvalidDocumentError(OCRError):
    """OCR 대상이 아닌 문서 상태이거나 이미 확정된 경우."""

    code = "INVALID_DOCUMENT"


class OCRTimeoutError(OCRError):
    """CLOVA OCR 호출이 타임아웃으로 종료된 경우."""

    code = "OCR_TIMEOUT"


class OCRClientError(OCRError):
    """CLOVA OCR 4xx — 요청 형식이나 인증 오류."""

    code = "OCR_CLIENT_ERROR"

    def __init__(self, message: str = "", status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class OCRServiceError(OCRError):
    """CLOVA OCR 5xx — 외부 서비스 불가용."""

    code = "OCR_SERVICE_UNAVAILABLE"

    def __init__(self, message: str = "", status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code
