"""OCR Worker 태스크 — KEY-56.

처리 흐름:
  CLOVA 활성  : 파일 읽기 → CLOVA 호출 → OcrResult/OcrDocumentText/OcrField 저장 → COMPLETED
  CLOVA 실패  : fixture fallback → COMPLETED  (전체 여정이 중단되지 않는다)
  CLOVA 비활성: fixture fallback → COMPLETED
  파일/DB 오류 : OcrJob.status → FAILED

필드 파싱 현황:
  현재는 CLOVA raw_text 전체를 단일 RAW_TEXT 필드로 저장한다.
  8/27 멘토링 후 문서 유형·핵심 필드 확정 시 _extract_fields() 함수를 교체한다 (step 6).
"""

import asyncio
from datetime import datetime
from pathlib import Path

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from ai_worker.adapters.clova import ClovaOcrError, ClovaOcrResult, call_clova_ocr
from ai_worker.core import config, default_logger
from app.models.documents import MedicalDocument
from app.models.ocr import (
    OcrDocumentText,
    OcrDocumentType,
    OcrField,
    OcrJob,
    OcrJobDocument,
    OcrJobStatus,
    OcrResult,
)
from app.ocr.service import seed_fixture_result

_CLOVA_MODEL_NAME = "clova-ocr-v2"


async def process_ocr_job(ocr_job_id: str) -> None:
    """Redis 큐에서 수신한 OCR 작업을 처리한다."""
    started_at = now()

    job = await OcrJob.filter(ocr_job_id=ocr_job_id).first()
    if job is None:
        default_logger.warning("OcrJob 없음 — ocr_job_id=%s", ocr_job_id)
        return
    if job.status != OcrJobStatus.PROCESSING:
        default_logger.warning("이미 처리된 작업 — ocr_job_id=%s, status=%s", ocr_job_id, job.status)
        return

    job.started_at = started_at
    await job.save(update_fields=("started_at",))

    job_documents = await OcrJobDocument.filter(ocr_job=job).all()
    if not job_documents:
        await _mark_failed(job, "NO_DOCUMENTS")
        return

    document_ids = [jd.document_id for jd in job_documents]
    medical_docs = await MedicalDocument.filter(document_id__in=document_ids).all()
    doc_map = {doc.document_id: doc for doc in medical_docs}

    if config.clova_enabled:
        try:
            clova_results = await _call_clova_for_documents(job_documents, doc_map)
            await _save_clova_result(job, job_documents, clova_results)
            _log_elapsed(ocr_job_id, "CLOVA", started_at)
        except ClovaOcrError as exc:
            default_logger.warning(
                "CLOVA 오류 → fixture fallback — ocr_job_id=%s, code=%s: %s",
                ocr_job_id,
                exc.code,
                exc,
            )
            await _fallback_or_fail(job, job_documents, ocr_job_id)
            _log_elapsed(ocr_job_id, "fixture(CLOVA 실패 후)", started_at)
        except Exception:
            default_logger.exception("OCR 처리 오류 → FAILED — ocr_job_id=%s", ocr_job_id)
            await _mark_failed(job, "PROCESSING_ERROR")
    else:
        default_logger.info("CLOVA 비활성 → fixture fallback — ocr_job_id=%s", ocr_job_id)
        await _fallback_or_fail(job, job_documents, ocr_job_id)
        _log_elapsed(ocr_job_id, "fixture", started_at)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _call_clova_for_documents(
    job_documents: list[OcrJobDocument],
    doc_map: dict[int, MedicalDocument],
) -> dict[int, ClovaOcrResult]:
    """문서마다 CLOVA OCR을 호출해 결과를 document_id → ClovaOcrResult로 반환한다."""
    results: dict[int, ClovaOcrResult] = {}
    for jd in job_documents:
        med_doc = doc_map.get(jd.document_id)
        if med_doc is None:
            raise RuntimeError(f"MedicalDocument 없음 — document_id={jd.document_id}")
        content = await asyncio.to_thread(Path(med_doc.file_path).read_bytes)
        results[jd.document_id] = await call_clova_ocr(content, med_doc.mime_type)
    return results


async def _save_clova_result(
    job: OcrJob,
    job_documents: list[OcrJobDocument],
    clova_results: dict[int, ClovaOcrResult],
) -> None:
    """CLOVA 결과를 OcrResult / OcrDocumentText / OcrField로 트랜잭션 안에 저장한다."""
    async with in_transaction() as conn:
        ocr_result = await OcrResult.create(
            ocr_job=job,
            model_name=_CLOVA_MODEL_NAME,
            using_db=conn,
        )
        first_doc_text: OcrDocumentText | None = None
        for jd in job_documents:
            clova_result = clova_results.get(jd.document_id)
            doc_text = await OcrDocumentText.create(
                ocr_result=ocr_result,
                document_id=jd.document_id,
                document_type=jd.document_type,
                raw_text=clova_result.raw_text if clova_result else None,
                using_db=conn,
            )
            if first_doc_text is None:
                first_doc_text = doc_text

        # TODO(KEY-56 step6): 8/27 멘토링 후 field_type별 파싱 로직으로 교체한다.
        # 현재는 첫 번째 문서의 텍스트를 RAW_TEXT 필드 하나로 저장해 수정·확정 계약을 유지한다.
        await _extract_fields(ocr_result, first_doc_text, job_documents, clova_results, conn)

        completed_at = now()
        job.status = OcrJobStatus.COMPLETED
        job.progress = 100
        job.completed_at = completed_at
        await job.save(
            update_fields=("status", "progress", "completed_at"),
            using_db=conn,
        )


async def _extract_fields(
    ocr_result: OcrResult,
    first_doc_text: OcrDocumentText | None,
    job_documents: list[OcrJobDocument],
    clova_results: dict[int, ClovaOcrResult],
    conn: BaseDBAsyncClient,
) -> None:
    """CLOVA 결과에서 OcrField를 생성한다.

    현재 구현: 첫 번째 문서의 raw_text를 RAW_TEXT 필드 하나로 저장한다.
    step 6에서 문서 유형별 핵심 필드 추출 로직으로 교체한다.
    """
    if not first_doc_text or not job_documents:
        return
    first_clova = clova_results.get(job_documents[0].document_id)
    if first_clova is None:
        return
    await OcrField.create(
        ocr_result=ocr_result,
        document_text=first_doc_text,
        field_type="RAW_TEXT",
        extracted_value=first_clova.raw_text[:500] if first_clova.raw_text else None,
        confidence=None,
        using_db=conn,
    )


async def _fallback_or_fail(
    job: OcrJob,
    job_documents: list[OcrJobDocument],
    ocr_job_id: str,
) -> None:
    """fixture fallback을 시도하고, 실패하면 FAILED로 전환한다."""
    try:
        async with in_transaction() as conn:
            await seed_fixture_result(
                job,
                [(jd.document_id, OcrDocumentType(jd.document_type)) for jd in job_documents],
                conn,
            )
    except Exception:
        default_logger.exception("fixture fallback도 실패 — ocr_job_id=%s", ocr_job_id)
        await _mark_failed(job, "FALLBACK_ERROR")


async def _mark_failed(job: OcrJob, failure_code: str) -> None:
    job.status = OcrJobStatus.FAILED
    job.failure_code = failure_code
    job.completed_at = now()
    await job.save(update_fields=("status", "failure_code", "completed_at"))


def _log_elapsed(ocr_job_id: str, mode: str, started_at: datetime) -> None:
    elapsed = (now() - started_at).total_seconds()
    default_logger.info(
        "OCR 처리 완료 — ocr_job_id=%s, 모드=%s, 소요시간=%.2fs",
        ocr_job_id,
        mode,
        elapsed,
    )
