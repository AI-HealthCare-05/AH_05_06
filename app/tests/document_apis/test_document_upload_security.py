"""KEY-55 파일 업로드 접근통제·악성 입력 회귀 테스트."""

from io import BytesIO

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.documents.api import document_router, get_document_service
from app.documents.schemas import DocumentUploadResponse
from app.documents.service import DocumentUploadService
from app.models.ocr import OcrJobStatus
from app.models.visits import Visit

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 32


class UnusedStorage:
    async def save(self, content: bytes, mime_type: str) -> str:
        raise AssertionError("validation tests must not save files")

    async def delete(self, path: str) -> None:
        raise AssertionError("validation tests must not delete files")


def _upload(filename: str, content: bytes, mime: str) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content), headers=Headers({"content-type": mime}))


async def _validate(filename: str, content: bytes, mime: str, *, max_bytes: int = 1024) -> None:
    service = DocumentUploadService(storage=UnusedStorage(), max_upload_bytes=max_bytes)
    await service._read_and_validate([_upload(filename, content, mime)])


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("record.jpg", JPEG_BYTES, "image/jpeg"),
        ("record.jpeg", JPEG_BYTES, "image/jpeg"),
        ("record.png", PNG_BYTES, "image/png"),
        ("record.pdf", PDF_BYTES, "application/pdf"),
    ],
)
async def test_allowed_file_extension_and_signature_are_accepted(filename: str, content: bytes, mime: str) -> None:
    await _validate(filename, content, mime)


@pytest.mark.parametrize("filename", ["payload.exe", "record.jpg.exe", "record"])
async def test_disallowed_or_missing_extension_is_rejected(filename: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        await _validate(filename, JPEG_BYTES, "image/jpeg")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_FILE_TYPE"


async def test_spoofed_mime_type_is_rejected_by_file_signature() -> None:
    with pytest.raises(ApiError) as exc_info:
        await _validate("malware.jpg", b"MZ" + b"\x00" * 32, "image/jpeg")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_FILE_TYPE"


@pytest.mark.parametrize("filename", ["../../record.jpg", "..\\..\\record.jpg"])
async def test_path_manipulation_filename_is_rejected(filename: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        await _validate(filename, JPEG_BYTES, "image/jpeg")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_FILE_TYPE"


async def test_actual_oversized_file_is_rejected() -> None:
    with pytest.raises(ApiError) as exc_info:
        await _validate("large.jpg", JPEG_BYTES, "image/jpeg", max_bytes=8)

    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "FILE_TOO_LARGE"


async def test_visit_access_query_always_includes_hospital_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, int] = {}

    class Query:
        async def exists(self) -> bool:
            return False

    def fake_filter(**kwargs: int) -> Query:
        captured.update(kwargs)
        return Query()

    monkeypatch.setattr(Visit, "filter", staticmethod(fake_filter))
    service = DocumentUploadService(storage=UnusedStorage(), max_upload_bytes=1024)

    with pytest.raises(ApiError) as exc_info:
        await service._verify_visit_access(visit_id=501, hospital_id=200)

    assert captured == {"visit_id": 501, "hospital_id": 200}
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "NOT_FOUND"


class FakeDocumentService:
    async def upload(self, **_) -> DocumentUploadResponse:
        return DocumentUploadResponse(document_ids=[1], ocr_job_id="ocr_synthetic", status=OcrJobStatus.PROCESSING)


def test_admin_only_actor_cannot_upload() -> None:
    app = FastAPI()
    app.include_router(document_router)
    app.dependency_overrides[get_clinical_actor] = lambda: ClinicalActor(
        staff_id=1,
        hospital_id=100,
        roles=frozenset({"admin"}),
    )
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService()

    response = TestClient(app, raise_server_exceptions=False).post(
        "/front-desk/visits/501/documents",
        files=[("files", ("record.jpg", BytesIO(JPEG_BYTES), "image/jpeg"))],
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
