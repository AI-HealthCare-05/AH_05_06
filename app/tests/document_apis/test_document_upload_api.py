"""
KEY-54 업로드 API 계층 테스트.

DB·스토리지를 사용하지 않는다. 서비스만 교체해 HTTP 계약(상태 코드·응답 스키마·에러 코드)을 검증한다.
"""

from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor, require_patient_access
from app.documents.api import document_router, get_document_service
from app.documents.schemas import DocumentUploadResponse
from app.models.ocr import OcrJobStatus

ACTOR = ClinicalActor(staff_id=1, hospital_id=100, roles=frozenset({"staff"}))
FAKE_RESPONSE = DocumentUploadResponse(
    document_ids=[801, 802],
    ocr_job_id="ocr_fake_abc123",
    status=OcrJobStatus.PROCESSING,
)

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JFIF 매직 바이트 포함 최소 더미
PDF_BYTES = b"%PDF-1.4 " + b"\x00" * 100


class FakeDocumentService:
    async def upload(self, *, visit_id, files, document_type, hospital_id, staff_id):
        return FAKE_RESPONSE


class FailDocumentService:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def upload(self, **_):
        raise self._exc


def make_client(service) -> TestClient:
    app = FastAPI()
    app.include_router(document_router)
    app.dependency_overrides[require_patient_access] = lambda: ACTOR
    app.dependency_overrides[get_document_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return make_client(FakeDocumentService())


# ── 정상 케이스 ──────────────────────────────────────────────────────────────


def test_upload_single_jpeg_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/front-desk/visits/501/documents",
        files=[("files", ("emr.jpg", BytesIO(JPEG_BYTES), "image/jpeg"))],
        data={"document_type": "EMR"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["document_ids"] == [801, 802]
    assert body["ocr_job_id"] == "ocr_fake_abc123"
    assert body["status"] == "PROCESSING"


def test_upload_pdf_without_document_type_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/front-desk/visits/501/documents",
        files=[("files", ("prescription.pdf", BytesIO(PDF_BYTES), "application/pdf"))],
    )
    assert resp.status_code == 201


def test_upload_multiple_files_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/front-desk/visits/501/documents",
        files=[
            ("files", ("page1.jpg", BytesIO(JPEG_BYTES), "image/jpeg")),
            ("files", ("page2.jpg", BytesIO(JPEG_BYTES), "image/jpeg")),
        ],
        data={"document_type": "PRESCRIPTION"},
    )
    assert resp.status_code == 201


# ── 예외 케이스 ──────────────────────────────────────────────────────────────


def test_invalid_file_type_returns_400() -> None:
    client = make_client(
        FailDocumentService(ApiError(400, "INVALID_FILE_TYPE", "지원하지 않는 파일 형식입니다. (허용: JPEG, PNG, PDF)"))
    )
    resp = client.post(
        "/front-desk/visits/501/documents",
        files=[("files", ("malware.exe", BytesIO(b"MZ" + b"\x00" * 50), "application/octet-stream"))],
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_visit_not_found_returns_404() -> None:
    client = make_client(FailDocumentService(ApiError(404, "NOT_FOUND", "진료 건을 찾을 수 없습니다.")))
    resp = client.post(
        "/front-desk/visits/99999/documents",
        files=[("files", ("emr.jpg", BytesIO(JPEG_BYTES), "image/jpeg"))],
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_file_too_large_returns_413() -> None:
    client = make_client(
        FailDocumentService(ApiError(413, "FILE_TOO_LARGE", "파일 크기가 제한을 초과합니다. (최대 20MB)"))
    )
    resp = client.post(
        "/front-desk/visits/501/documents",
        files=[("files", ("huge.jpg", BytesIO(JPEG_BYTES), "image/jpeg"))],
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "FILE_TOO_LARGE"


def test_unauthenticated_request_returns_401() -> None:
    from app.core.auth_errors import TOKEN_EXPIRED, AuthError
    from app.core.error_handlers import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)
    app.add_exception_handler(
        AuthError,
        lambda _, exc: __import__("fastapi").responses.JSONResponse(
            status_code=exc.status_code, content={"code": exc.code}
        ),
    )
    app.include_router(document_router)
    # 인증 의존성이 AuthError 401 을 던지도록 교체
    app.dependency_overrides[require_patient_access] = lambda: (_ for _ in ()).throw(
        AuthError(TOKEN_EXPIRED, 401, "로그인이 필요합니다.")
    )
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/front-desk/visits/501/documents",
        files=[("files", ("emr.jpg", BytesIO(JPEG_BYTES), "image/jpeg"))],
    )
    assert resp.status_code == 401


def test_invalid_visit_id_returns_400(client: TestClient) -> None:
    # ContractRoute 가 RequestValidationError → 400 INVALID_REQUEST 로 변환한다.
    resp = client.post(
        "/front-desk/visits/not-a-number/documents",
        files=[("files", ("emr.jpg", BytesIO(JPEG_BYTES), "image/jpeg"))],
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"
