"""KEY-266: OCR enqueue 실패 시 저장 파일·문서/작업 row를 정리한다.

인수조건:
- Redis rpush 실패 시 saved_paths 파일이 모두 삭제된다.
- OcrJobDocument / OcrJob / MedicalDocument row가 모두 삭제된다.
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

    async def update(self, **_kwargs: object) -> None:
        pass


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
) -> tuple[_DeleteCapture, _DeleteCapture, _DeleteCapture]:
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

    job_doc_cap = _DeleteCapture()
    job_cap = _DeleteCapture()
    doc_cap = _DeleteCapture()
    monkeypatch.setattr(OcrJobDocument, "filter", job_doc_cap)
    monkeypatch.setattr(OcrJob, "filter", job_cap)
    monkeypatch.setattr(MedicalDocument, "filter", doc_cap)

    return job_doc_cap, job_cap, doc_cap


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

    # storage.save를 intercept해 upload()가 저장한 경로를 추적한다.
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
    # upload()가 save한 경로가 모두 delete 됐는지 확인
    assert set(captured_paths) == set(storage.deleted), (
        f"저장된 경로 {captured_paths!r} 중 삭제되지 않은 파일이 있습니다: {storage.deleted!r}"
    )


async def test_enqueue_failure_deletes_db_rows(
    service: DocumentUploadService,
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enqueue 실패 시 OcrJobDocument / OcrJob / MedicalDocument row가 모두 삭제된다."""
    job_doc_cap, job_cap, doc_cap = _patch_common(service, monkeypatch, document_ids=[10], ocr_job_ids=["ocr_xyz"])

    await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert job_doc_cap.deleted, "OcrJobDocument.filter(...).delete()가 호출되지 않았습니다."
    assert job_cap.deleted, "OcrJob.filter(...).delete()가 호출되지 않았습니다."
    assert doc_cap.deleted, "MedicalDocument.filter(...).delete()가 호출되지 않았습니다."

    assert job_doc_cap.filter_kwargs == {"ocr_job_id__in": ["ocr_xyz"]}
    assert job_cap.filter_kwargs == {"ocr_job_id__in": ["ocr_xyz"]}
    assert doc_cap.filter_kwargs == {"document_id__in": [10]}


async def test_enqueue_failure_cleanup_error_preserves_response(
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """정리 중 예외가 발생해도 응답 계약(status, ids)은 유지된다."""
    error_storage = _ErrorStorage()
    service = DocumentUploadService(storage=error_storage, max_upload_bytes=1024 * 1024)

    job_doc_cap, job_cap, doc_cap = _patch_common(service, monkeypatch, document_ids=[20], ocr_job_ids=["ocr_err"])

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
    """순단 → 재업로드 N회 반복 후 고아 파일·row가 누적되지 않는다.

    매 업로드마다 다른 document_id / ocr_job_id 세트를 사용하고,
    각 실패 직후 정리가 완료됐는지 누적 삭제 수로 확인한다.
    """
    service = DocumentUploadService(storage=storage, max_upload_bytes=1024 * 1024)

    call_count = 0
    all_job_doc_deletes: list[bool] = []
    all_job_deletes: list[bool] = []
    all_doc_deletes: list[bool] = []

    for i in range(3):
        doc_id = 100 + i
        job_id = f"ocr_repeat_{i}"

        job_doc_cap, job_cap, doc_cap = _patch_common(service, monkeypatch, document_ids=[doc_id], ocr_job_ids=[job_id])

        original_save = storage.save

        async def tracking_save(content: bytes, mime_type: str, _orig=original_save) -> str:
            return await _orig(content, mime_type)

        monkeypatch.setattr(storage, "save", tracking_save)

        await service.upload(
            visit_id=501,
            files=[jpeg_file],
            document_type=None,
            hospital_id=100,
            staff_id=1,
        )
        call_count += 1

        # 이번 업로드에서 저장한 파일이 즉시 삭제됐는지 확인
        assert len(storage.deleted) == len(storage.saved), (
            f"반복 {i}: 저장 {len(storage.saved)}개 중 {len(storage.deleted)}개만 삭제됨"
        )
        all_job_doc_deletes.append(job_doc_cap.deleted)
        all_job_deletes.append(job_cap.deleted)
        all_doc_deletes.append(doc_cap.deleted)

    assert call_count == 3
    assert all(all_job_doc_deletes), "일부 반복에서 OcrJobDocument 삭제가 누락됐습니다."
    assert all(all_job_deletes), "일부 반복에서 OcrJob 삭제가 누락됐습니다."
    assert all(all_doc_deletes), "일부 반복에서 MedicalDocument 삭제가 누락됐습니다."
    # 저장과 삭제 수가 같아야 고아가 0
    assert len(storage.saved) == len(storage.deleted), (
        f"전체 저장 {len(storage.saved)}개, 삭제 {len(storage.deleted)}개 — 고아 파일이 남아 있습니다."
    )
