"""OCR_FIXTURE_FALLBACK 단일 소유 검증 — KEY-199.

fixture seed는 업로드(_persist)가 단독으로 소유한다.
워커는 OCR_FIXTURE_FALLBACK 값과 무관하게 CLOVA 실패 시 항상 FAILED로 처리한다.

DB 없이 DocumentUploadService.upload의 큐잉 분기만 검증한다.
  - OCR_FIXTURE_FALLBACK=true  → _persist 완료 후 Redis rpush 호출하지 않는다
  - OCR_FIXTURE_FALLBACK=false → _persist 완료 후 Redis rpush에 ocr_job_id를 넣는다
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.documents.service import OCR_JOB_QUEUE, DocumentUploadService
from app.models.ocr import OcrDocumentType

_FAKE_JOB_ID = "ocr_key199_test"
_FAKE_DOC_IDS = [42]


def _make_service() -> DocumentUploadService:
    return DocumentUploadService(storage=AsyncMock(), max_upload_bytes=10_000_000)


def _mock_upload_file(mime: str = "image/jpeg", filename: str = "test.jpg") -> MagicMock:
    f = MagicMock()
    f.content_type = mime
    f.filename = filename
    return f


async def _run_upload(service: DocumentUploadService, fallback: bool) -> AsyncMock:
    """업로드를 실행하고 redis mock을 반환한다."""
    mock_redis = AsyncMock()
    with (
        patch.object(
            service, "_read_and_validate", AsyncMock(return_value=[(b"\xff\xd8" + b"\x00" * 8, "image/jpeg")])
        ),
        patch.object(service, "_verify_visit_access", AsyncMock()),
        patch.object(service, "_persist", AsyncMock(return_value=(_FAKE_DOC_IDS, _FAKE_JOB_ID))),
        patch("app.documents.service.config") as mock_cfg,
        patch("app.documents.service.get_redis", return_value=mock_redis),
    ):
        mock_cfg.OCR_FIXTURE_FALLBACK = fallback
        await service.upload(
            visit_id=1,
            files=[_mock_upload_file()],
            document_type=OcrDocumentType.EMR,
            hospital_id=1,
            staff_id=1,
        )
    return mock_redis


# ── OCR_FIXTURE_FALLBACK=true → 큐잉 없음 ───────────────────────────────────


async def test_fixture_fallback_on_skips_redis_enqueue() -> None:
    """OCR_FIXTURE_FALLBACK=true이면 _persist가 이미 COMPLETED로 처리했으므로 큐에 넣지 않는다."""
    service = _make_service()
    mock_redis = await _run_upload(service, fallback=True)

    mock_redis.rpush.assert_not_awaited()


# ── OCR_FIXTURE_FALLBACK=false → 큐잉 ───────────────────────────────────────


async def test_fixture_fallback_off_enqueues_job_to_redis() -> None:
    """OCR_FIXTURE_FALLBACK=false이면 업로드 후 워커 큐에 ocr_job_id를 넣는다."""
    service = _make_service()
    mock_redis = await _run_upload(service, fallback=False)

    mock_redis.rpush.assert_awaited_once_with(OCR_JOB_QUEUE, _FAKE_JOB_ID)


# ── 이중 처리 없음 ────────────────────────────────────────────────────────────


async def test_no_double_processing_regardless_of_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OCR_FIXTURE_FALLBACK 값에 따라 큐잉과 직접 seed 중 정확히 하나만 실행된다.

    true  → seed 경로(rpush 0회)
    false → 큐잉 경로(rpush 1회)
    둘 다 동시에 실행되는 이중 처리가 없음을 확인한다.
    """
    service = _make_service()

    redis_on = await _run_upload(service, fallback=True)
    redis_off = await _run_upload(service, fallback=False)

    assert redis_on.rpush.await_count == 0, "fallback=true 시 rpush가 호출됐다 — 이중 처리"
    assert redis_off.rpush.await_count == 1, "fallback=false 시 rpush가 호출되지 않았다 — 무처리"
