"""AI Worker 진입점 — KEY-56.

Redis 큐(ocr:jobs)를 polling하며 OCR 작업을 순차 처리한다.
SIGTERM·SIGINT 수신 시 현재 작업을 마친 뒤 종료한다.
"""

import asyncio
import signal

from tortoise import Tortoise

from ai_worker.core import config, default_logger
from ai_worker.tasks.ocr_task import process_ocr_job
from app.core.db.databases import WORKER_TORTOISE_ORM
from app.core.redis_client import close_redis, get_redis
from app.documents.service import OCR_JOB_QUEUE

# blpop 타임아웃(초) — 이 간격마다 _shutdown 플래그를 확인한다.
_BLPOP_TIMEOUT = 5

_shutdown = False


def _request_shutdown(sig: int, _: object) -> None:
    global _shutdown
    default_logger.info("종료 신호 수신 (signal=%d) — 현재 작업 완료 후 종료", sig)
    _shutdown = True


async def _run() -> None:
    default_logger.info(
        "AI Worker 시작 — CLOVA: %s",
        "활성" if config.clova_enabled else "fixture fallback",
    )

    await Tortoise.init(config=WORKER_TORTOISE_ORM)
    default_logger.info("DB 연결 완료")

    redis = get_redis()

    try:
        while not _shutdown:
            # timeout 초 동안 대기; 작업이 없으면 None 반환 → 루프 반복
            item = await redis.blpop([OCR_JOB_QUEUE], timeout=_BLPOP_TIMEOUT)  # type: ignore[misc]
            if item is None:
                continue

            _, ocr_job_id = item
            default_logger.info("OCR 작업 수신 — ocr_job_id=%s", ocr_job_id)

            try:
                await process_ocr_job(ocr_job_id)
            except Exception:
                # 태스크 내부에서 OcrJob.status를 FAILED로 처리하는 것이 원칙이다.
                # 여기까지 올라온 예외는 태스크 외부의 예상치 못한 오류이므로 기록만 한다.
                default_logger.exception("OCR 작업 처리 중 예상치 못한 예외 — ocr_job_id=%s", ocr_job_id)
    finally:
        await Tortoise.close_connections()
        await close_redis()
        default_logger.info("AI Worker 종료 완료")


def main() -> None:
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
