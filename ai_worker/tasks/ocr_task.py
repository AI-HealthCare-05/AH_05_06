"""OCR Worker 태스크 — KEY-56 · KEY-175.

처리 흐름:
  CLOVA 활성                  : 파일 읽기 → CLOVA 호출 → OcrResult/OcrDocumentText/OcrField 저장 → COMPLETED
  CLOVA 활성 + 필수 필드 누락 : REQUIRED_FIELD_MISSING 설정 → fixture fallback 또는 FAILED
  CLOVA 실패                  : CLOVA_API_ERROR 설정 → fixture fallback 또는 FAILED
  CLOVA 비활성                : OCR_NOT_CONFIGURED 설정 → fixture fallback 또는 FAILED
  파일/DB 오류                : OcrJob.status → FAILED

  필수 필드(DIAGNOSIS·MEDICATION_NAME·DURATION_DAYS) 중 하나라도 누락되면
  CLOVA 호출 자체가 성공해도 COMPLETED로 처리하지 않는다 (KEY-163 §4, KEY-187).

필드 파싱:
  와이어프레임 S1-6~9 근거로 문서 유형별 핵심 필드를 추출한다 (field_extractor.py).
  EMR은 CLOVA 블록 파서(헤더→값 레이아웃) 우선, 실패한 필드만 정규식으로 보완한다.

관측 로그 (KEY-175):
  모든 종료 경로에서 아래 형식의 단일 구조화 로그를 남긴다.
  ocr_job_complete mode=<clova|fixture|failed> elapsed_ms=<n> clova_elapsed_ms=<n|none> error_code=<code|none> ocr_job_id=<id>
  - clova_elapsed_ms: 실제 CLOVA HTTP 호출 시간 합계, 성공 경로에서만 기록
  - 환자정보·OCR 원문·파일 경로·오류 원문은 로그에 포함하지 않는다.
"""

import asyncio
from pathlib import Path
from time import perf_counter

from tortoise.timezone import now
from tortoise.transactions import in_transaction

from ai_worker.adapters.clova import ClovaOcrError, ClovaOcrResult, call_clova_ocr
from ai_worker.core import config, default_logger
from ai_worker.tasks.field_extractor import ExtractedField, extract_fields
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

# EMR 문서가 포함된 작업에서 COMPLETED로 인정하려면 이 필드를 모두 추출해야 한다 (KEY-163 §4, KEY-187)
_REQUIRED_OCR_FIELDS: frozenset[str] = frozenset({"DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"})


async def process_ocr_job(ocr_job_id: str) -> None:
    """Redis 큐에서 수신한 OCR 작업을 처리한다."""
    t0 = perf_counter()
    started_at = now()

    job = await OcrJob.filter(ocr_job_id=ocr_job_id).first()
    if job is None:
        default_logger.warning("OcrJob 없음 — ocr_job_id=%s", ocr_job_id)
        _observe(ocr_job_id=ocr_job_id, mode="failed", t0=t0, error_code="JOB_NOT_FOUND")
        return
    if job.status != OcrJobStatus.PROCESSING:
        default_logger.warning("이미 처리된 작업 — ocr_job_id=%s, status=%s", ocr_job_id, job.status)
        _observe(ocr_job_id=ocr_job_id, mode="failed", t0=t0, error_code="ALREADY_PROCESSED")
        return

    job.started_at = started_at
    await job.save(update_fields=("started_at",))

    job_documents = await OcrJobDocument.filter(ocr_job=job).all()
    if not job_documents:
        await _mark_failed(job, "NO_DOCUMENTS")
        _observe(ocr_job_id=ocr_job_id, mode="failed", t0=t0, error_code="NO_DOCUMENTS")
        return

    document_ids = [jd.document_id for jd in job_documents]
    medical_docs = await MedicalDocument.filter(document_id__in=document_ids).all()
    doc_map = {doc.document_id: doc for doc in medical_docs}

    if config.clova_enabled:
        try:
            clova_results = await _call_clova_for_documents(job_documents, doc_map)
            clova_elapsed_ms = sum(r.elapsed_ms for r in clova_results.values())
            saved = await _save_clova_result(job, job_documents, clova_results)
            if saved:
                _observe(ocr_job_id=ocr_job_id, mode="clova", t0=t0, error_code=None, clova_elapsed_ms=clova_elapsed_ms)
            else:
                job.failure_code = "REQUIRED_FIELD_MISSING"
                await job.save(update_fields=("failure_code",))
                used_fixture = await _fallback_or_fail(job, job_documents, ocr_job_id)
                default_logger.warning(
                    "필수 OCR 필드 누락 → %s — ocr_job_id=%s",
                    "fixture fallback" if used_fixture else "FAILED",
                    ocr_job_id,
                )
                _observe(
                    ocr_job_id=ocr_job_id,
                    mode="fixture" if used_fixture else "failed",
                    t0=t0,
                    error_code="REQUIRED_FIELD_MISSING",
                    clova_elapsed_ms=clova_elapsed_ms,
                )
        except ClovaOcrError as exc:
            job.failure_code = "CLOVA_API_ERROR"
            await job.save(update_fields=("failure_code",))
            used_fixture = await _fallback_or_fail(job, job_documents, ocr_job_id)
            default_logger.warning(
                "CLOVA 오류 → %s — ocr_job_id=%s, code=%s",
                "fixture fallback" if used_fixture else "FAILED",
                ocr_job_id,
                exc.code,
            )
            _observe(
                ocr_job_id=ocr_job_id,
                mode="fixture" if used_fixture else "failed",
                t0=t0,
                error_code=exc.code,
                clova_elapsed_ms=exc.elapsed_ms,
            )
        except Exception as exc:
            default_logger.error(
                "OCR 처리 오류 — ocr_job_id=%s, error_type=%s",
                ocr_job_id,
                type(exc).__name__,
                exc_info=False,
            )
            await _mark_failed(job, "PROCESSING_ERROR")
            _observe(ocr_job_id=ocr_job_id, mode="failed", t0=t0, error_code="PROCESSING_ERROR")
    else:
        job.failure_code = "OCR_NOT_CONFIGURED"
        await job.save(update_fields=("failure_code",))
        used_fixture = await _fallback_or_fail(job, job_documents, ocr_job_id)
        default_logger.warning(
            "CLOVA 미설정 → %s — ocr_job_id=%s",
            "fixture fallback" if used_fixture else "FAILED",
            ocr_job_id,
        )
        _observe(
            ocr_job_id=ocr_job_id,
            mode="fixture" if used_fixture else "failed",
            t0=t0,
            error_code="OCR_NOT_CONFIGURED",
        )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _call_clova_for_documents(
    job_documents: list[OcrJobDocument],
    doc_map: dict[int, MedicalDocument],
) -> dict[int, ClovaOcrResult]:
    """문서마다 CLOVA OCR을 호출해 결과를 document_id → ClovaOcrResult로 반환한다."""
    results: dict[int, ClovaOcrResult] = {}
    accumulated_ms = 0
    for jd in job_documents:
        med_doc = doc_map.get(jd.document_id)
        if med_doc is None:
            raise RuntimeError(f"MedicalDocument 없음 — document_id={jd.document_id}")
        content = await asyncio.to_thread(Path(med_doc.file_path).read_bytes)
        try:
            result = await call_clova_ocr(content, med_doc.mime_type)
        except ClovaOcrError as exc:
            has_timing = accumulated_ms > 0 or exc.elapsed_ms is not None
            elapsed_ms = (accumulated_ms + (exc.elapsed_ms or 0)) if has_timing else None
            raise ClovaOcrError(exc.code, str(exc), elapsed_ms=elapsed_ms) from exc
        accumulated_ms += result.elapsed_ms
        results[jd.document_id] = result
    return results


def _extract_fields_per_doc(
    job_documents: list[OcrJobDocument],
    clova_results: dict[int, ClovaOcrResult],
) -> tuple[list[tuple[OcrJobDocument, list[ExtractedField]]], set[str], bool]:
    """문서별로 필드를 추출해 (fields_by_doc, emr_field_types, has_emr)을 반환한다.

    emr_field_types는 EMR 문서에서 추출된 field_type만 포함한다 (필수 필드 게이트 전용).
    """
    fields_by_doc: list[tuple[OcrJobDocument, list[ExtractedField]]] = []
    emr_field_types: set[str] = set()
    has_emr = False
    for jd in job_documents:
        doc_type = OcrDocumentType(jd.document_type)
        if doc_type == OcrDocumentType.EMR:
            has_emr = True
        clova_result = clova_results.get(jd.document_id)
        if clova_result is None:
            continue
        fields = extract_fields(clova_result, doc_type)
        fields_by_doc.append((jd, fields))
        if doc_type == OcrDocumentType.EMR:
            emr_field_types.update(f.field_type for f in fields)
    return fields_by_doc, emr_field_types, has_emr


async def _save_clova_result(
    job: OcrJob,
    job_documents: list[OcrJobDocument],
    clova_results: dict[int, ClovaOcrResult],
) -> bool:
    """CLOVA 결과를 OcrResult / OcrDocumentText / OcrField로 트랜잭션 안에 저장한다.

    EMR 문서가 포함된 경우 필수 필드(DIAGNOSIS·MEDICATION_NAME·DURATION_DAYS)가
    모두 추출되어야 COMPLETED로 처리한다. 하나라도 누락이면 False를 반환한다.
    """
    # Phase 1: 필드 추출 — 트랜잭션 밖에서 수행해 불필요한 롤백 방지
    fields_by_doc, emr_field_types, has_emr = _extract_fields_per_doc(job_documents, clova_results)

    # Phase 2: EMR이 포함된 경우 필수 필드 게이트 — EMR 문서 추출 필드만 검사 (KEY-163 §4)
    if has_emr and not (_REQUIRED_OCR_FIELDS <= emr_field_types):
        return False

    # Phase 3: 트랜잭션 안에서 DB 저장
    async with in_transaction() as conn:
        ocr_result = await OcrResult.create(
            ocr_job=job,
            model_name=_CLOVA_MODEL_NAME,
            using_db=conn,
        )
        doc_text_map: dict[int, OcrDocumentText] = {}
        for jd in job_documents:
            clova_result = clova_results.get(jd.document_id)
            doc_text = await OcrDocumentText.create(
                ocr_result=ocr_result,
                document_id=jd.document_id,
                document_type=jd.document_type,
                raw_text=clova_result.raw_text if clova_result else None,
                using_db=conn,
            )
            doc_text_map[jd.document_id] = doc_text

        seen_types: set[str] = set()
        for jd, fields in fields_by_doc:
            if jd.document_id not in doc_text_map:
                continue
            doc_text = doc_text_map[jd.document_id]
            for field in fields:
                if field.field_type in seen_types:
                    continue
                seen_types.add(field.field_type)
                await OcrField.create(
                    ocr_result=ocr_result,
                    document_text=doc_text,
                    field_type=field.field_type,
                    extracted_value=field.extracted_value,
                    confidence=field.confidence,
                    using_db=conn,
                )

        completed_at = now()
        job.status = OcrJobStatus.COMPLETED
        job.progress = 100
        job.completed_at = completed_at
        await job.save(
            update_fields=("status", "progress", "completed_at"),
            using_db=conn,
        )

    return True


async def _fallback_or_fail(
    job: OcrJob,
    job_documents: list[OcrJobDocument],
    ocr_job_id: str,
) -> bool:
    """fixture fallback을 시도한다. fixture 성공이면 True, FAILED 전환이면 False를 반환한다.

    OCR_FIXTURE_FALLBACK이 비활성(로컬 외 환경 또는 명시적으로 꺼진 경우)이면
    fixture를 심지 않고 즉시 FAILED로 전환한다.
    """
    if not config.OCR_FIXTURE_FALLBACK:
        default_logger.warning(
            "fixture fallback 비활성 → FAILED 처리 — ocr_job_id=%s, ENV=%s",
            ocr_job_id,
            config.ENV,
        )
        await _mark_failed(job, job.failure_code or "PROCESSING_ERROR")
        return False
    try:
        async with in_transaction() as conn:
            await seed_fixture_result(
                job,
                [(jd.document_id, OcrDocumentType(jd.document_type)) for jd in job_documents],
                conn,
            )
        # fixture 성공 시 failure_code 초기화 — COMPLETED 상태에서 UI 오류 문구 방지
        job.failure_code = None  # type: ignore[assignment]  # CharField(null=True)
        await job.save(update_fields=("failure_code",))
        return True
    except Exception as exc:
        default_logger.error(
            "fixture fallback도 실패 — ocr_job_id=%s, error_type=%s",
            ocr_job_id,
            type(exc).__name__,
            exc_info=False,
        )
        await _mark_failed(job, "FALLBACK_ERROR")
        return False


async def _mark_failed(job: OcrJob, failure_code: str) -> None:
    job.status = OcrJobStatus.FAILED
    job.failure_code = failure_code
    job.completed_at = now()
    await job.save(update_fields=("status", "failure_code", "completed_at"))


def _observe(
    *,
    ocr_job_id: str,
    mode: str,
    t0: float,
    error_code: str | None,
    clova_elapsed_ms: int | None = None,
) -> None:
    """모든 OCR 종료 경로에서 단일 구조화 메트릭 로그를 남긴다 (KEY-175).

    mode: clova | fixture | failed
    clova_elapsed_ms: 실제 CLOVA HTTP 호출 시간 합계 (성공 경로에서만 제공)
    환자정보·OCR 원문·파일 경로·오류 원문은 포함하지 않는다.
    """
    elapsed_ms = round((perf_counter() - t0) * 1000)
    default_logger.info(
        "ocr_job_complete mode=%s elapsed_ms=%s clova_elapsed_ms=%s error_code=%s ocr_job_id=%s",
        mode,
        elapsed_ms,
        clova_elapsed_ms if clova_elapsed_ms is not None else "none",
        error_code or "none",
        ocr_job_id,
    )
