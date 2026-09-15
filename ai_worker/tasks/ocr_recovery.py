"""큐에서 꺼낸 뒤 중단된 OCR 작업을 실패로 종료한다 — KEY-154.

재큐잉하지 않는다. FAILED의 기존 재업로드 경로로 복구한다.
"""

from datetime import datetime, timedelta

from tortoise.expressions import Q
from tortoise.timezone import now

from ai_worker.core import default_logger
from app.models.ocr import OcrJob, OcrJobStatus

# 파일 하나당 CLOVA 10초 × 최대 3회 + backoff 1.5초에 파일/DB 처리 여유를 둔다.
# 워커 중복 배포 시 정상 실행을 끊지 않도록, 시작 여부가 아니라 경과 시간으로 판정한다.
PROCESSING_TIMEOUT = timedelta(minutes=10)
PROCESSING_TIMEOUT_CODE = "PROCESSING_TIMEOUT"
RECOVERY_INTERVAL_SECONDS = 60


async def expire_stale_ocr_jobs(*, at: datetime | None = None) -> int:
    """후보 조회 뒤에도 상태·시각을 다시 조건으로 걸어 정상 완료/새 시작을 보호한다."""
    checked_at = at or now()
    cutoff = checked_at - PROCESSING_TIMEOUT
    stale = Q(started_at__lte=cutoff) | Q(started_at__isnull=True, created_at__lte=cutoff)
    ids = await OcrJob.filter(stale, status=OcrJobStatus.PROCESSING).values_list("ocr_job_id", flat=True)
    count = 0
    for job_id in ids:
        changed = await OcrJob.filter(stale, ocr_job_id=job_id, status=OcrJobStatus.PROCESSING).update(
            status=OcrJobStatus.FAILED,
            failure_code=PROCESSING_TIMEOUT_CODE,
            progress=0,
            completed_at=checked_at,
            updated_at=checked_at,
        )
        if changed:
            count += 1
            default_logger.warning("ocr_job_id=%s code=%s", job_id, PROCESSING_TIMEOUT_CODE)
    return count
