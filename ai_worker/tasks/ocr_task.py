"""OCR Worker 태스크 — KEY-56 · KEY-175.

처리 흐름:
  CLOVA 활성                  : 파일 읽기 → CLOVA 호출 → OcrResult/OcrDocumentText/OcrField 저장 → COMPLETED
  CLOVA 활성 + 필수 필드 누락 : **빈 줄로 저장하고 COMPLETED** — 화면이 물음표로 세우고 사람이 채운다
  CLOVA 실패                  : CLOVA_API_ERROR 설정 → FAILED
  CLOVA 비활성                : OCR_NOT_CONFIGURED 설정 → FAILED
  파일/DB 오류                : OcrJob.status → FAILED

  필수 필드(DIAGNOSIS·MEDICATION_NAME·DURATION_DAYS) 중 못 읽은 것은
  **값이 빈 OcrField 로 남긴다** (KEY-163 §4, KEY-187).

  예전에는 하나라도 없으면 작업 전체를 FAILED 로 보냈다. 그러면 OcrResult
  자체가 안 생겨서 화면에 채워 넣을 항목 목록이 없었고, 스탭은 「판독하지
  못했습니다」 앞에서 막혔다 — 사진은 멀쩡한데 표 한 칸을 못 읽어서 진료가
  멈추는 모양이다. 빈 줄을 남기면 화면이 물음표로 세우고 사람이 눈으로 읽어
  채운다. 못 읽은 횟수는 로그와 관측 줄(error_code)에 남는다.

필드 파싱:
  와이어프레임 S1-6~9 근거로 문서 유형별 핵심 필드를 추출한다 (field_extractor.py).
  EMR은 CLOVA 블록 파서(헤더→값 레이아웃) 우선, 실패한 필드만 정규식으로 보완한다.

관측 로그 (KEY-175):
  모든 종료 경로에서 아래 형식의 단일 구조화 로그를 남긴다.
  ocr_job_complete mode=<clova|failed> elapsed_ms=<n> clova_elapsed_ms=<n|none> error_code=<code|none> ocr_job_id=<id>
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

_CLOVA_MODEL_NAME = "clova-ocr-v2"

# EMR 문서가 포함된 작업에서 COMPLETED로 인정하려면 이 필드를 모두 추출해야 한다 (KEY-163 §4, KEY-187)
_REQUIRED_OCR_FIELDS: frozenset[str] = frozenset({"DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"})

# CLOVA 일시 오류 — 재시도 대상 코드 (KEY-227)
# 5xx·429·timeout·connection-error는 일시적, 4xx는 확정 실패로 재시도하지 않는다
_RETRYABLE_CLOVA_CODES: frozenset[str] = frozenset(
    {
        "CLOVA_TIMEOUT",  # httpx.TimeoutException
        "CLOVA_NETWORK_ERROR",  # httpx.RequestError (연결 리셋·DNS·read)
        "CLOVA_SERVER_ERROR",  # HTTP 5xx / 429
    }
)
_MAX_CLOVA_RETRIES = 2


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
        retry_count = 0
        partial_results: dict[int, ClovaOcrResult] = {}
        while True:
            try:
                clova_results = await _call_clova_for_documents(job_documents, doc_map, partial_results)
                clova_elapsed_ms = sum(r.elapsed_ms for r in clova_results.values())
                missing = await _save_clova_result(job, job_documents, clova_results)
                if missing:
                    # **작업은 성공이다.** 못 읽은 항목은 빈 줄로 남아 있고, 화면이
                    # 그 자리를 물음표로 세워 사람이 채운다. 판독은 거들 뿐이라,
                    # 표 한 칸을 못 읽었다고 진료를 멈추지 않는다.
                    #
                    # 다만 **얼마나 자주 못 읽는지는 남긴다.** 이것이 안 보이면
                    # 추출기가 나빠지는 것을 아무도 모른 채 스탭 손이 늘어난다.
                    default_logger.warning(
                        "필수 OCR 필드 누락 — 빈 줄로 저장 · ocr_job_id=%s, fields=%s",
                        ocr_job_id,
                        ",".join(sorted(missing)),
                    )
                _observe(
                    ocr_job_id=ocr_job_id,
                    mode="clova",
                    t0=t0,
                    error_code="REQUIRED_FIELD_MISSING" if missing else None,
                    clova_elapsed_ms=clova_elapsed_ms,
                    retry_count=retry_count,
                )
                break
            except ClovaOcrError as exc:
                if exc.code in _RETRYABLE_CLOVA_CODES and retry_count < _MAX_CLOVA_RETRIES:
                    retry_count += 1
                    default_logger.warning(
                        "CLOVA 일시 오류 재시도 — ocr_job_id=%s, code=%s, attempt=%d/%d",
                        ocr_job_id,
                        exc.code,
                        retry_count,
                        _MAX_CLOVA_RETRIES,
                    )
                    await asyncio.sleep(0.5 * retry_count)
                    continue
                await _mark_failed(job, "CLOVA_API_ERROR")
                default_logger.warning(
                    "CLOVA 오류 → FAILED — ocr_job_id=%s, code=%s, retry_count=%d",
                    ocr_job_id,
                    exc.code,
                    retry_count,
                )
                _observe(
                    ocr_job_id=ocr_job_id,
                    mode="failed",
                    t0=t0,
                    error_code=exc.code,
                    clova_elapsed_ms=exc.elapsed_ms,
                    retry_count=retry_count,
                )
                break
            except Exception as exc:
                default_logger.error(
                    "OCR 처리 오류 — ocr_job_id=%s, error_type=%s",
                    ocr_job_id,
                    type(exc).__name__,
                    exc_info=False,
                )
                await _mark_failed(job, "PROCESSING_ERROR")
                _observe(
                    ocr_job_id=ocr_job_id, mode="failed", t0=t0, error_code="PROCESSING_ERROR", retry_count=retry_count
                )
                break
    else:
        await _mark_failed(job, "OCR_NOT_CONFIGURED")
        default_logger.warning("CLOVA 미설정 → FAILED — ocr_job_id=%s", ocr_job_id)
        _observe(
            ocr_job_id=ocr_job_id,
            mode="failed",
            t0=t0,
            error_code="OCR_NOT_CONFIGURED",
        )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _call_clova_for_documents(
    job_documents: list[OcrJobDocument],
    doc_map: dict[int, MedicalDocument],
    results: dict[int, ClovaOcrResult] | None = None,
) -> dict[int, ClovaOcrResult]:
    """문서마다 CLOVA OCR을 호출해 결과를 document_id → ClovaOcrResult로 반환한다.

    results에 이미 성공한 문서가 있으면 해당 문서는 재호출하지 않는다.
    재시도 시 같은 dict를 전달하면 성공한 문서를 중복 호출하지 않는다.
    """
    if results is None:
        results = {}
    accumulated_ms = sum(r.elapsed_ms for r in results.values())
    for jd in job_documents:
        if jd.document_id in results:
            continue
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
) -> set[str]:
    """CLOVA 결과를 OcrResult / OcrDocumentText / OcrField로 트랜잭션 안에 저장한다.

    EMR 문서가 포함됐는데 필수 필드(DIAGNOSIS·MEDICATION_NAME·DURATION_DAYS)를
    못 읽었으면 **값이 빈 줄을 대신 남기고** 저장을 계속한다.
    못 읽은 필드 이름을 돌려준다 (없으면 빈 집합).

    예전에는 여기서 False를 돌려주고 작업 전체를 FAILED로 보냈다. 그러면
    OcrResult 자체가 안 생겨서 화면에 채워 넣을 항목 목록이 없었고, 스탭은
    「판독하지 못했습니다」 한 판 앞에서 막혔다 — 사진은 멀쩡한데 표 한 칸을
    못 읽어서 진료가 멈추는 모양이다.

    빈 줄을 남기면 화면이 그 자리를 물음표로 세우고 사람이 눈으로 읽어
    채운다(`PATCH /ocr/fields/{id}`). 판독은 거들 뿐이고, 못 읽었다고
    진료가 멈추면 안 된다.

    **빈 줄과 「값이 0이다」는 다르다.** `extracted_value=None` 이고
    `confidence=None` 이라, 화면은 이것을 「못 읽음」으로 그린다
    (`fieldState` — 값이 없으면 missing). 사람이 확정하기 전에는 안내문에도
    안 실린다(`is_confirmed=False`).
    """
    # Phase 1: 필드 추출 — 트랜잭션 밖에서 수행해 불필요한 롤백 방지
    fields_by_doc, emr_field_types, has_emr = _extract_fields_per_doc(job_documents, clova_results)

    # Phase 2: EMR이 포함된 경우 못 읽은 필수 필드를 센다 (KEY-163 §4)
    #
    # EMR이 없는 작업(검사 결과지만 올린 경우)에는 처방 항목이 애초에 없다.
    # 그때 빈 줄을 만들면 안 한 것을 못 읽은 것처럼 보인다.
    missing = sorted(_REQUIRED_OCR_FIELDS - emr_field_types) if has_emr else []

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

        # 못 읽은 필수 항목은 **빈 줄로 남긴다.** 어느 문서에서 나올 값인지
        # 모르므로 document_text는 비운다 (모델이 null을 허용한다).
        for field_type in missing:
            if field_type in seen_types:
                continue
            await OcrField.create(
                ocr_result=ocr_result,
                document_text=None,
                field_type=field_type,
                extracted_value=None,
                confidence=None,
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

    return set(missing)


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
    retry_count: int = 0,
) -> None:
    """모든 OCR 종료 경로에서 단일 구조화 메트릭 로그를 남긴다 (KEY-175).

    mode: clova | failed
    clova_elapsed_ms: 실제 CLOVA HTTP 호출 시간 합계 (성공 경로에서만 제공)
    retry_count: 재시도 횟수 (KEY-227)
    환자정보·OCR 원문·파일 경로·오류 원문은 포함하지 않는다.
    """
    elapsed_ms = round((perf_counter() - t0) * 1000)
    default_logger.info(
        "ocr_job_complete mode=%s elapsed_ms=%s clova_elapsed_ms=%s error_code=%s retry_count=%s ocr_job_id=%s",
        mode,
        elapsed_ms,
        clova_elapsed_ms if clova_elapsed_ms is not None else "none",
        error_code or "none",
        retry_count,
        ocr_job_id,
    )
