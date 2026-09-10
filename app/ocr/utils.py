"""OCR 공통 유틸 — 여러 서비스 레이어에서 공유하는 함수."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from fastapi import status

from app.models.ocr import OcrDocumentType, OcrJob, OcrJobStatus
from app.ocr.errors import OcrApiError

if TYPE_CHECKING:
    from app.models.ocr import OcrField, OcrResult

# 같은 확정 상태에서 문서 유형 간 우선순위 — 낮을수록 우선
_DOC_TYPE_PRIORITY: dict[OcrDocumentType, int] = {
    OcrDocumentType.EMR: 0,
    OcrDocumentType.PRESCRIPTION: 1,
    OcrDocumentType.LAB_RESULT: 2,
}


async def assert_ocr_jobs_ready(visit_id: int, hospital_id: int) -> list[OcrJob]:
    """비제외 전체 OCR job을 검증하고 COMPLETED job 목록을 반환한다.

    - 최신 COMPLETED job보다 나중에 생성된 PROCESSING job이 있으면 차단한다.
      같은 업로드 배치의 형제 파일 job이 아직 처리 중임을 의미한다.
    - 최신 COMPLETED보다 오래된 PROCESSING job(방치·고착)은 무시한다.
    - FAILED job은 안내 근거에서 제외하고 COMPLETED job 목록에 포함하지 않는다.
    - COMPLETED job이 없으면 차단한다.

    finalize_ocr(app/ocr/service.py)과 generate(app/services/guides.py) 양쪽이
    이 함수를 호출해 동일한 기준으로 job을 선택한다.
    """
    jobs = (
        await OcrJob.filter(
            visit_id=visit_id,
            hospital_id=hospital_id,
            excluded_from_guide=False,
        )
        .order_by("-created_at")
        .all()
    )

    if not jobs:
        raise OcrApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "OCR_NOT_CONFIRMED",
            "확정된 OCR 항목이 없습니다. 먼저 OCR을 확정해 주세요.",
        )

    # FAILED job은 안내 근거에서 제외하고 COMPLETED job만 수집한다 (KEY-288 AC 3).
    # 파일 하나가 실패해도 나머지 COMPLETED job으로 안내를 생성할 수 있다.
    completed = [j for j in jobs if j.status == OcrJobStatus.COMPLETED]

    if not completed:
        if any(j.status == OcrJobStatus.PROCESSING for j in jobs):
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "OCR_RESULT_NOT_READY",
                "OCR 판독이 아직 처리 중입니다. 완료 후 확정해 주세요.",
            )
        raise OcrApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "OCR_FAILED",
            "가장 최근 판독이 실패했습니다. 재시도하거나 해당 판독을 제외해 주세요.",
        )

    # completed[0]은 -created_at 정렬 기준 최신 COMPLETED job.
    # 이보다 나중에 생성된 PROCESSING job이 있으면 같은 배치의 형제 파일이 처리 중이므로 차단한다.
    # 최신 COMPLETED보다 오래된 PROCESSING은 방치·고착 job으로 보고 무시한다.
    newest_completed = completed[0]
    if any(
        j.status == OcrJobStatus.PROCESSING and j.created_at > newest_completed.created_at
        for j in jobs
    ):
        raise OcrApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "OCR_RESULT_NOT_READY",
            "같은 업로드 배치의 파일이 아직 처리 중입니다. 완료 후 확정해 주세요.",
        )

    return completed


def merge_fields_by_type(
    results: Iterable[OcrResult],
    *,
    doc_type_of: dict[int, OcrDocumentType] | None = None,
) -> dict[str, OcrField]:
    """여러 OcrResult의 필드를 field_type별로 병합한다.

    confirmed > unconfirmed, 동급이면 문서 유형 우선순위(EMR>PRESCRIPTION>LAB_RESULT),
    같으면 confidence 높은 쪽을 택한다.
    doc_type_of가 없으면 문서 유형 우선순위를 적용하지 않고 confidence만 비교한다.
    """
    best: dict[str, OcrField] = {}
    for result in results:
        for field in result.fields:
            existing = best.get(field.field_type)
            if existing is None:
                best[field.field_type] = field
            elif not existing.is_confirmed and field.is_confirmed:
                best[field.field_type] = field
            elif existing.is_confirmed == field.is_confirmed and _field_wins(field, existing, doc_type_of):
                best[field.field_type] = field
    return best


def _field_wins(
    candidate: OcrField,
    existing: OcrField,
    doc_type_of: dict[int, OcrDocumentType] | None,
) -> bool:
    """같은 확정 상태에서 candidate가 existing보다 우선인지 판단한다.

    doc_type_of가 있으면 문서 유형 우선순위를 먼저 비교하고, 동급이면 confidence로 tiebreak한다.
    """
    if doc_type_of is not None:
        cp = _doc_priority(candidate.ocr_result_id, doc_type_of)
        ep = _doc_priority(existing.ocr_result_id, doc_type_of)
        if cp != ep:
            return cp < ep
    cc = float(candidate.confidence) if candidate.confidence is not None else 0.0
    ec = float(existing.confidence) if existing.confidence is not None else 0.0
    return cc > ec


def _doc_priority(result_id: int, doc_type_of: dict[int, OcrDocumentType]) -> int:
    dt = doc_type_of.get(result_id)
    return _DOC_TYPE_PRIORITY.get(dt, 99) if dt is not None else 99


def ocr_doc_type_priority(doc_type: OcrDocumentType | None) -> int:
    """문서 유형 우선순위를 반환한다 — 낮을수록 우선 (EMR=0, PRESCRIPTION=1, LAB_RESULT=2, 미지=99)."""
    if doc_type is None:
        return 99
    return _DOC_TYPE_PRIORITY.get(doc_type, 99)
