"""AI Worker 진입점 — KEY-56.

Redis 큐(ocr:jobs)를 polling하며 OCR 작업을 순차 처리한다. 예약된 안내·확인
문자(GuideMessage)도 같은 프로세스 안에서 별도 주기로 집어서 보낸다 — KEY-249.
SIGTERM·SIGINT 수신 시 현재 작업을 마친 뒤 종료한다.
"""

import asyncio
import signal

from tortoise import Tortoise

from ai_worker.core import config, default_logger
from ai_worker.tasks.ocr_task import process_ocr_job
from app.core.config import Config
from app.core.db.databases import WORKER_TORTOISE_ORM
from app.core.redis_client import close_redis, get_redis
from app.documents.service import OCR_JOB_QUEUE
from app.services.guide_generation_jobs import process_next_generation
from app.services.message_dispatch import dispatch_due_messages
from app.services.sms_sender import build_sms_sender

# blpop 타임아웃(초) — 이 간격마다 _shutdown 플래그를 확인한다.
_BLPOP_TIMEOUT = 5
# 예약 문자를 몇 초마다 확인할지 — OCR과 달리 큐가 아니라 시각 기반이라
# polling으로 본다.
_MESSAGE_POLL_SECONDS = 30

_shutdown = False


def _request_shutdown(sig: int, _: object) -> None:
    global _shutdown
    default_logger.info("종료 신호 수신 (signal=%d) — 현재 작업 완료 후 종료", sig)
    _shutdown = True


async def _run_ocr_loop() -> None:
    redis = get_redis()
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


async def _run_message_dispatch_loop() -> None:
    """`_MESSAGE_POLL_SECONDS`마다 나갈 때가 된 안내·확인 문자를 찾아서 보낸다 — KEY-249.

    SMS 설정 오류(SMS_PROVIDER=solapi인데 시크릿이 비어 있는 등)로 발송기
    생성 자체가 실패해도, 그건 이 루프만 못 뛰는 것이지 OCR 처리까지 죽을
    이유는 없다 — 두 파이프라인은 서로 독립적이어야 한다(2heej 리뷰).
    """
    try:
        sender = build_sms_sender(Config())
    except Exception:
        default_logger.exception("문자 발송기 생성 실패 — 이 프로세스에서는 예약 문자 발송을 하지 않는다")
        return

    while not _shutdown:
        try:
            results = await dispatch_due_messages(sender)
            if results:
                default_logger.info("예약 문자 처리 — %d건", len(results))
        except Exception:
            # 한 주기에서 예상치 못한 예외가 나도 다음 주기에 다시 시도한다 —
            # 여기서 죽으면 그 뒤로 어떤 예약 문자도 안 나간다.
            default_logger.exception("예약 문자 처리 중 예상치 못한 예외")
        for _ in range(_MESSAGE_POLL_SECONDS):
            if _shutdown:
                break
            await asyncio.sleep(1)


async def _run_guide_generation_loop() -> None:
    enabled = Config().GUIDE_RAG_ENABLED
    while not _shutdown:
        if enabled:
            try:
                await process_next_generation()
            except Exception:
                default_logger.error("안내 생성 작업 큐 조회 실패")
        await asyncio.sleep(1)


async def _run() -> None:
    default_logger.info(
        "AI Worker 시작 — CLOVA: %s",
        "활성" if config.clova_enabled else "fixture fallback",
    )

    await Tortoise.init(config=WORKER_TORTOISE_ORM)
    default_logger.info("DB 연결 완료")

    try:
        # return_exceptions=True — 한쪽이 예상치 못하게 죽어도 다른 쪽까지
        # asyncio.gather가 취소시키지 않는다. OCR과 문자 발송은 서로 남의
        # 사정으로 멈추면 안 되는 별개 파이프라인이다(2heej 리뷰).
        results = await asyncio.gather(
            _run_ocr_loop(), _run_message_dispatch_loop(), _run_guide_generation_loop(), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                default_logger.exception("Worker 루프가 예상치 못하게 종료됨", exc_info=result)
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
