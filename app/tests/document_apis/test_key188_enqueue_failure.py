"""KEY-188: OCR 큐 enqueue 실패 시 업로드 API가 FAILED 상태를 즉시 반환한다.

Redis rpush가 일시 실패할 때 OcrJob이 PROCESSING으로 무기한 방치되지 않고
응답 status가 FAILED로 반환된다.
파일·row 정리 동작은 test_key266_enqueue_cleanup.py 에서 검증한다.
"""

import types
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import app.documents.service as doc_service
from app.documents.service import DocumentUploadService
from app.models.ocr import OcrJob, OcrJobStatus


class _FakeStorage:
    async def save(self, content: bytes, mime_type: str) -> str:
        return "fake/path.jpg"

    async def delete(self, path: str) -> None:
        pass


class _BrokenRedis:
    async def rpush(self, *_args: object) -> None:
        raise ConnectionError("Redis 연결 끊김")


class _UpdateQS:
    async def update(self, **_kwargs: object) -> None:
        pass


@pytest.fixture()
def service() -> DocumentUploadService:
    return DocumentUploadService(storage=_FakeStorage(), max_upload_bytes=1024 * 1024)


@pytest.fixture()
def jpeg_file() -> UploadFile:
    return UploadFile(
        filename="emr.jpg",
        file=BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 32),
        headers=Headers({"content-type": "image/jpeg"}),
    )


async def test_redis_enqueue_failure_returns_failed_status(
    service: DocumentUploadService,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_validate(_files):  # type: ignore[no-untyped-def]
        return [(b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")]

    async def fake_verify(*, visit_id: int, hospital_id: int) -> None:
        pass

    async def fake_persist(**_kwargs: object) -> tuple[list[int], list[str]]:
        return ([1], ["ocr_test_abc123"])

    monkeypatch.setattr(service, "_read_and_validate", fake_validate)
    monkeypatch.setattr(service, "_verify_visit_access", fake_verify)
    monkeypatch.setattr(service, "_persist", fake_persist)

    monkeypatch.setattr(doc_service, "config", types.SimpleNamespace(OCR_FIXTURE_FALLBACK=False))
    monkeypatch.setattr(doc_service, "get_redis", lambda: _BrokenRedis())
    monkeypatch.setattr(OcrJob, "filter", staticmethod(lambda **_: _UpdateQS()))

    result = await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert result.status == OcrJobStatus.FAILED
    assert result.ocr_job_ids == ["ocr_test_abc123"]


async def test_redis_enqueue_success_returns_processing_status(
    service: DocumentUploadService,
    jpeg_file: UploadFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """정상 enqueue 시 기존 PROCESSING 반환 경로가 유지된다."""

    async def fake_validate(_files):  # type: ignore[no-untyped-def]
        return [(b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")]

    async def fake_verify(*, visit_id: int, hospital_id: int) -> None:
        pass

    async def fake_persist(**_kwargs: object) -> tuple[list[int], list[str]]:
        return ([1], ["ocr_test_ok123"])

    monkeypatch.setattr(service, "_read_and_validate", fake_validate)
    monkeypatch.setattr(service, "_verify_visit_access", fake_verify)
    monkeypatch.setattr(service, "_persist", fake_persist)

    monkeypatch.setattr(doc_service, "config", types.SimpleNamespace(OCR_FIXTURE_FALLBACK=False))

    class _OkRedis:
        async def rpush(self, *_args: object) -> int:
            return 1

    monkeypatch.setattr(doc_service, "get_redis", lambda: _OkRedis())

    result = await service.upload(
        visit_id=501,
        files=[jpeg_file],
        document_type=None,
        hospital_id=100,
        staff_id=1,
    )

    assert result.status == OcrJobStatus.PROCESSING
    assert result.ocr_job_ids == ["ocr_test_ok123"]
