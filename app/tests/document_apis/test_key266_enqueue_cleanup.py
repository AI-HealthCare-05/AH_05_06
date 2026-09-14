"""KEY-266: OCR enqueue 실패 시 OcrJob을 FAILED로 남겨 타임라인 가시성을 보장한다.

인수조건:
- Redis rpush 실패 시 파일·MedicalDocument·OcrJob row를 삭제하지 않는다.
- OcrJob 상태를 FAILED로 업데이트한다.
- 업데이트 자체가 실패해도 응답 계약(status=FAILED, document_ids, ocr_job_ids)은 유지된다.
"""

import types
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import app.documents.service as doc_service
from app.documents.service import DocumentUploadService
from app.models.ocr import OcrJob, OcrJobStatus

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


class _BrokenUpdateCapture(_UpdateCapture):
    async def update(self, **_kwargs: object) -> None:
        raise RuntimeError("DB 업데이트 실패")


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
) -> _UpdateCapture:
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
    monkeypatch.setattr(OcrJob, "filter", job_cap)

    return job_cap


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


async def test_enqueue_failure_keeps_files(
    service: DocumentUploadService,
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enqueue 실패 시 저장된 파일을 삭제하지 않아 경로 추적이 가능하다."""
    _patch_common(service, monkeypatch, document_ids=[1], ocr_job_ids=["ocr_abc"])

    await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert len(storage.saved) == 1
    assert len(storage.deleted) == 0, f"파일이 삭제되면 안 되는데 삭제됐습니다: {storage.deleted!r}"


async def test_enqueue_failure_marks_ocr_job_failed(
    service: DocumentUploadService,
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enqueue 실패 시 OcrJob 상태가 FAILED로 업데이트된다."""
    job_cap = _patch_common(service, monkeypatch, document_ids=[10], ocr_job_ids=["ocr_xyz"])

    result = await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert result.status == OcrJobStatus.FAILED
    assert job_cap.updated, "OcrJob.filter(...).update(status=FAILED)가 호출되지 않았습니다."
    assert job_cap.filter_kwargs == {"ocr_job_id__in": ["ocr_xyz"]}
    assert job_cap.update_kwargs == {"status": OcrJobStatus.FAILED}


async def test_enqueue_failure_update_error_preserves_response(
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OcrJob 업데이트 자체가 실패해도 응답 계약(status, ids)은 유지된다."""
    service = DocumentUploadService(storage=storage, max_upload_bytes=1024 * 1024)

    async def fake_validate(_files):  # type: ignore[no-untyped-def]
        return [(b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")]

    async def fake_verify(*, visit_id: int, hospital_id: int) -> None:
        pass

    async def fake_persist(**_kwargs: object) -> tuple[list[int], list[str]]:
        return ([20], ["ocr_err"])

    monkeypatch.setattr(service, "_read_and_validate", fake_validate)
    monkeypatch.setattr(service, "_verify_visit_access", fake_verify)
    monkeypatch.setattr(service, "_persist", fake_persist)
    monkeypatch.setattr(doc_service, "config", types.SimpleNamespace(OCR_FIXTURE_FALLBACK=False))
    monkeypatch.setattr(doc_service, "get_redis", lambda: _BrokenRedis())
    monkeypatch.setattr(OcrJob, "filter", _BrokenUpdateCapture())

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


async def test_repeated_enqueue_failures_accumulate_failed_rows(
    storage: _TrackingStorage,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """순단 → 재업로드 N회 반복 후 매 실패마다 OcrJob이 FAILED로 남는다."""
    service = DocumentUploadService(storage=storage, max_upload_bytes=1024 * 1024)

    for i in range(3):
        doc_id = 100 + i
        job_id = f"ocr_repeat_{i}"

        job_cap = _UpdateCapture()

        async def fake_validate(_files):  # type: ignore[no-untyped-def]
            return [(b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")]

        async def fake_verify(*, visit_id: int, hospital_id: int) -> None:
            pass

        def _make_fake_persist(d: int, j: str):  # type: ignore[no-untyped-def]
            async def _persist(**_kwargs: object) -> tuple[list[int], list[str]]:
                return ([d], [j])
            return _persist

        fake_persist = _make_fake_persist(doc_id, job_id)

        monkeypatch.setattr(service, "_read_and_validate", fake_validate)
        monkeypatch.setattr(service, "_verify_visit_access", fake_verify)
        monkeypatch.setattr(service, "_persist", fake_persist)
        monkeypatch.setattr(doc_service, "config", types.SimpleNamespace(OCR_FIXTURE_FALLBACK=False))
        monkeypatch.setattr(doc_service, "get_redis", lambda: _BrokenRedis())
        monkeypatch.setattr(OcrJob, "filter", job_cap)

        result = await service.upload(
            visit_id=501,
            files=[jpeg_file],
            document_type=None,
            hospital_id=100,
            staff_id=1,
        )

        assert result.status == OcrJobStatus.FAILED
        assert job_cap.updated, f"반복 {i}: OcrJob FAILED 업데이트가 누락됐습니다."
        assert job_cap.filter_kwargs == {"ocr_job_id__in": [job_id]}

    # 파일은 삭제되지 않고 누적된다
    assert len(storage.saved) == 3
    assert len(storage.deleted) == 0
