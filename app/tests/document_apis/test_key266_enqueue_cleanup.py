"""KEY-266: OCR enqueue 실패 시 OcrJob은 FAILED로 유지하고 고아 파일·row를 정리한다.

인수조건:
- Redis rpush 실패 시 saved_paths 파일과 MedicalDocument·OcrJobDocument row가 삭제된다.
- OcrJob은 삭제하지 않고 status=FAILED, failure_code=QUEUE_ERROR, completed_at으로 업데이트한다.
- 정리 중 예외가 발생해도 응답 계약(status=FAILED, document_ids, ocr_job_ids)은 유지된다.
"""

import types
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import app.documents.service as doc_service
from app.documents.service import DocumentUploadService
from app.models.documents import MedicalDocument
from app.models.ocr import OcrJob, OcrJobDocument, OcrJobStatus

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


class _TrackingStorage:
    def __init__(self) -> None:
        self.saved: list[str] = []
        self.deleted: list[str] = []

    async def save(self, content: bytes, mime_type: str) -> str:
        path = f"fake/{len(self.saved)}.jpg"
        self.saved.append(path)
        return path

    async def delete(self, path: str) -> None:
        self.deleted.append(path)


class _BrokenRedis:
    async def rpush(self, *_args: object) -> None:
        raise ConnectionError("Redis 연결 끊김")


class _UpdateCapture:
    """filter(**kwargs).update(**kwargs) 호출을 추적하는 가짜 QuerySet."""

    def __init__(self) -> None:
        self.updated = False
        self.filter_kwargs: dict = {}
        self.update_kwargs: dict = {}

    def __call__(self, **kwargs: object) -> "_UpdateCapture":
        self.filter_kwargs = dict(kwargs)
        return self

    async def update(self, **kwargs: object) -> None:
        self.updated = True
        self.update_kwargs = dict(kwargs)


class _DeleteCapture:
    """filter(**kwargs).delete() 호출을 추적하는 가짜 QuerySet."""

    def __init__(self) -> None:
        self.deleted = False
        self.filter_kwargs: dict = {}

    def __call__(self, **kwargs: object) -> "_DeleteCapture":
        self.filter_kwargs = dict(kwargs)
        return self

    async def delete(self) -> None:
        self.deleted = True


class _ErrorStorage(_TrackingStorage):
    async def delete(self, path: str) -> None:
        raise OSError("스토리지 삭제 실패")


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage() -> _TrackingStorage:
    return _TrackingStorage()


@pytest.fixture()
def service(storage: _TrackingStorage) -> DocumentUploadService:
    return DocumentUploadService(storage=storage, max_upload_bytes=1024 * 1024)


@pytest.fixture()
def jpeg_file() -> UploadFile:
    return UploadFile(
        filename="emr.jpg",
        file=BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 32),
        headers=Headers({"content-type": "image/jpeg"}),
    )


def _patch_common(
    service: DocumentUploadService,
    monkeypatch: pytest.MonkeyPatch,
    *,
    document_ids: list[int],
    ocr_job_ids: list[str],
) -> tuple[_UpdateCapture, _DeleteCapture, _DeleteCapture]:
    async def fake_validate(_files):  # type: ignore[no-untyped-def]
        return [(b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")] * len(document_ids)

    async def fake_verify(*, visit_id: int, hospital_id: int) -> None:
        pass

    async def fake_persist(**_kwargs: object) -> tuple[list[int], list[str]]:
        return (document_ids, ocr_job_ids)

    monkeypatch.setattr(service, "_read_and_validate", fake_validate)
    monkeypatch.setattr(service, "_verify_visit_access", fake_verify)
    monkeypatch.setattr(service, "_persist", fake_persist)
    monkeypatch.setattr(doc_service, "config", types.SimpleNamespace(OCR_FIXTURE_FALLBACK=False))
    monkeypatch.setattr(doc_service, "get_redis", lambda: _BrokenRedis())

    job_cap = _UpdateCapture()
    job_doc_cap = _DeleteCapture()
    doc_cap = _DeleteCapture()
    monkeypatch.setattr(OcrJob, "filter", job_cap)
    monkeypatch.setattr(OcrJobDocument, "filter", job_doc_cap)
    monkeypatch.setattr(MedicalDocument, "filter", doc_cap)

    return job_cap, job_doc_cap, doc_cap


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


async def test_enqueue_failure_deletes_saved_files(
    service: DocumentUploadService,
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enqueue 실패 시 저장된 모든 파일이 storage에서 삭제된다."""
    _patch_common(service, monkeypatch, document_ids=[1], ocr_job_ids=["ocr_abc"])

    original_save = storage.save
    captured_paths: list[str] = []

    async def tracking_save(content: bytes, mime_type: str) -> str:
        path = await original_save(content, mime_type)
        captured_paths.append(path)
        return path

    monkeypatch.setattr(storage, "save", tracking_save)

    result = await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert result.status == OcrJobStatus.FAILED
    assert set(captured_paths) == set(storage.deleted), (
        f"저장된 경로 {captured_paths!r} 중 삭제되지 않은 파일이 있습니다: {storage.deleted!r}"
    )


async def test_enqueue_failure_marks_ocr_job_failed(
    service: DocumentUploadService,
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enqueue 실패 시 OcrJob이 FAILED·QUEUE_ERROR·completed_at으로 업데이트된다."""
    job_cap, _, _ = _patch_common(service, monkeypatch, document_ids=[10], ocr_job_ids=["ocr_xyz"])

    result = await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert result.status == OcrJobStatus.FAILED
    assert job_cap.updated, "OcrJob.filter(...).update()가 호출되지 않았습니다."
    assert job_cap.filter_kwargs == {"ocr_job_id__in": ["ocr_xyz"]}
    assert job_cap.update_kwargs["status"] == OcrJobStatus.FAILED
    assert job_cap.update_kwargs["failure_code"] == "QUEUE_ERROR"
    assert "completed_at" in job_cap.update_kwargs


async def test_enqueue_failure_deletes_db_rows(
    service: DocumentUploadService,
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enqueue 실패 시 OcrJobDocument·MedicalDocument row가 삭제된다."""
    _, job_doc_cap, doc_cap = _patch_common(service, monkeypatch, document_ids=[10], ocr_job_ids=["ocr_xyz"])

    await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert job_doc_cap.deleted, "OcrJobDocument.filter(...).delete()가 호출되지 않았습니다."
    assert job_doc_cap.filter_kwargs == {"ocr_job_id__in": ["ocr_xyz"]}
    assert doc_cap.deleted, "MedicalDocument.filter(...).delete()가 호출되지 않았습니다."
    assert doc_cap.filter_kwargs == {"document_id__in": [10]}


async def test_enqueue_failure_cleanup_error_preserves_response(
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """정리 중 예외가 발생해도 응답 계약(status, ids)은 유지된다."""
    error_storage = _ErrorStorage()
    service = DocumentUploadService(storage=error_storage, max_upload_bytes=1024 * 1024)
    _patch_common(service, monkeypatch, document_ids=[20], ocr_job_ids=["ocr_err"])

    result = await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert result.status == OcrJobStatus.FAILED
    assert result.document_ids == [20]
    assert result.ocr_job_ids == ["ocr_err"]


async def test_repeated_enqueue_failures_leave_no_orphans(
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """순단 → 재업로드 N회 반복 후 고아 파일·row 수가 0으로 유지된다."""
    service = DocumentUploadService(storage=storage, max_upload_bytes=1024 * 1024)

    for i in range(3):
        doc_id = 100 + i
        job_id = f"ocr_repeat_{i}"

        job_cap, job_doc_cap, doc_cap = _patch_common(service, monkeypatch, document_ids=[doc_id], ocr_job_ids=[job_id])

        captured_paths: list[str] = []
        deleted_before = len(storage.deleted)

        def _make_tracking_save(  # type: ignore[no-untyped-def]
            orig, paths: list[str]
        ):
            async def _save(content: bytes, mime_type: str) -> str:
                path = await orig(content, mime_type)
                paths.append(path)
                return path

            return _save

        monkeypatch.setattr(storage, "save", _make_tracking_save(storage.save, captured_paths))

        await service.upload(
            visit_id=501,
            files=[jpeg_file],
            document_type=None,
            hospital_id=100,
            staff_id=1,
        )

        newly_deleted = storage.deleted[deleted_before:]
        assert set(captured_paths) == set(newly_deleted), (
            f"반복 {i}: 저장 {captured_paths!r} 중 미삭제 파일 존재: {newly_deleted!r}"
        )
        assert job_cap.updated, f"반복 {i}: OcrJob FAILED 업데이트가 누락됐습니다."
        assert job_doc_cap.deleted, f"반복 {i}: OcrJobDocument 삭제가 누락됐습니다."
        assert doc_cap.deleted, f"반복 {i}: MedicalDocument 삭제가 누락됐습니다."
