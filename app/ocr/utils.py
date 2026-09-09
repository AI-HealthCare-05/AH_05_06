"""OCR 공통 유틸 — 여러 서비스 레이어에서 공유하는 함수."""

from fastapi import status

from app.models.ocr import OcrJob, OcrJobStatus
from app.ocr.errors import OcrApiError


async def assert_latest_ocr_job_ready(visit_id: int, hospital_id: int) -> OcrJob:
    """최신 비제외 job 상태를 검증하고 COMPLETED job을 반환한다.

    재업로드가 처리 중·실패이면 이전 확정값만으로 안내가 생성되거나 처방이
    세워지는 것을 막는다. excluded_from_guide=True job은 직원이 제외한
    문서이므로 건너뛴다.

    finalize_ocr(app/ocr/service.py)과 generate(app/services/guides.py) 양쪽이
    이 함수를 호출해 동일한 기준으로 job을 선택한다.
    """
    latest_job = (
        await OcrJob.filter(
            visit_id=visit_id,
            hospital_id=hospital_id,
            excluded_from_guide=False,
        )
        .order_by("-created_at")
        .first()
    )

    if latest_job is None:
        raise OcrApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "OCR_NOT_CONFIRMED",
            "확정된 OCR 항목이 없습니다. 먼저 OCR을 확정해 주세요.",
        )

    if latest_job.status == OcrJobStatus.PROCESSING:
        raise OcrApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "OCR_RESULT_NOT_READY",
            "가장 최근 판독이 아직 처리 중입니다. 완료 후 확정해 주세요.",
        )

    if latest_job.status == OcrJobStatus.FAILED:
        raise OcrApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "OCR_FAILED",
            "가장 최근 판독이 실패했습니다. 재시도하거나 해당 판독을 제외해 주세요.",
        )

    return latest_job
