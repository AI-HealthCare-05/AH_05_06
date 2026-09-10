"""Database-backed generation queue and bounded retries for KEY-277."""

import json
import logging
from datetime import timedelta
from functools import lru_cache
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core import config
from app.core.auth_errors import AuthError as ApiError
from app.models.catalog import DoctorGuideCopy
from app.models.ocr import OcrField, OcrJob, OcrResult
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.staffs import Staff, StaffStatus
from app.models.visits import (
    GuideDocument,
    GuideGenerationJob,
    GuideSafetyCheck,
    GuideSection,
    GuideSectionSourceSnapshot,
    SafetyCheckStage,
    SafetyCheckVerdict,
    Visit,
)
from app.services.guide_generation import GuideGenerationError
from app.services.safety_check import CHECKER_VERSION, SafetyReasonCode

LOGGER = logging.getLogger("app.guide_generation")
MAX_ATTEMPTS = 3
LEASE_SECONDS = 300


@lru_cache(maxsize=1)
def build_generator():
    """One pinned embedding model per worker process, loaded only when enabled."""
    from app.services.approved_knowledge_search import ApprovedKnowledgeSearchService
    from app.services.chatbot import OpenAIResponsesModel
    from app.services.guide_generation import RagGuideGenerator
    from app.services.knowledge_pipeline import LocalSentenceTransformerEmbeddingProvider

    key = config.OPENAI_API_KEY.get_secret_value() if config.OPENAI_API_KEY else ""
    return RagGuideGenerator(
        ApprovedKnowledgeSearchService(LocalSentenceTransformerEmbeddingProvider()),
        OpenAIResponsesModel(
            api_key=key,
            model_name=config.OPENAI_MODEL,
            base_url=config.OPENAI_BASE_URL,
            timeout_seconds=config.OPENAI_TIMEOUT_SECONDS,
        )
        if key.strip()
        else None,
    )


class GenerationPendingError(Exception):
    def __init__(self, job: GuideGenerationJob) -> None:
        self.job = job


async def record_failure(job: GuideGenerationJob, exc: GuideGenerationError | ApiError) -> None:
    reason = exc.reason if isinstance(exc, GuideGenerationError) else str(exc.code)
    retry = isinstance(exc, GuideGenerationError) and exc.retryable and job.attempts < MAX_ATTEMPTS
    async with in_transaction() as conn:
        changed = (
            await GuideGenerationJob.filter(job_id=job.pk, claim=job.claim, active_key__not_isnull=True)
            .using_db(conn)
            .update(
                failure_reason=reason[:60],
                available_at=now() + timedelta(seconds=2**job.attempts),
                failed_at=None if retry else now(),
                active_key=job.active_key if retry else None,
            )
        )
        if changed and isinstance(exc, GuideGenerationError) and reason.upper() in {v.value for v in SafetyReasonCode}:
            await GuideSafetyCheck.create(
                generation_job=job,
                guide_document=None,
                section_key=exc.section_key,
                stage=SafetyCheckStage.POST_GENERATE if exc.stage == "post" else SafetyCheckStage.PRE_GENERATE,
                verdict=SafetyCheckVerdict.BLOCK,
                reason_code=reason.upper(),
                checker_version=CHECKER_VERSION,
                using_db=conn,
            )
    if changed and not retry:
        LOGGER.error("guide_generation_failed reason=%s job=%s", reason, job.pk)


async def input_checksum(visit_id: int) -> str:
    """A change detector only; raw OCR values never enter the queue or prompt."""
    jobs = await OcrJob.filter(visit_id=visit_id).order_by("created_at", "ocr_job_id").values()
    results = await OcrResult.filter(ocr_job_id__in=[j["ocr_job_id"] for j in jobs]).values_list(
        "ocr_result_id", flat=True
    )
    fields = await OcrField.filter(ocr_result_id__in=results).order_by("ocr_field_id").values()
    prescriptions = await Prescription.filter(visit_id=visit_id).order_by("prescription_id").values()
    items = (
        await PrescriptionItem.filter(prescription_id__in=[p["prescription_id"] for p in prescriptions])
        .order_by("prescription_item_id")
        .values()
    )
    visit = await Visit.get(visit_id=visit_id)
    guides = await GuideDocument.filter(visit_id=visit_id).values("guide_document_id", "version", "status")
    sections = await GuideSection.filter(guide_document__visit_id=visit_id).order_by("guide_section_id").values()
    copies = await DoctorGuideCopy.filter(hospital_id=visit.hospital_id).order_by("doctor_guide_copy_id").values()
    return sha256(
        json.dumps(
            [jobs, fields, prescriptions, items, visit.doctor_id, guides, sections, copies], sort_keys=True, default=str
        ).encode()
    ).hexdigest()


async def enqueue(actor, visit_id: int, *, discard_edits: bool) -> GuideGenerationJob:
    from app.services.guides import REGENERABLE, _no_regenerate_saying

    async with in_transaction() as conn:
        visit = (
            await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if visit is None:
            raise ApiError("VISIT_NOT_FOUND", 404, "진료 건을 찾을 수 없습니다.")
        guide = await GuideDocument.filter(visit_id=visit_id).using_db(conn).first()
        if guide and guide.status not in REGENERABLE:
            raise ApiError("GUIDE_ALREADY_EXISTS", 409, _no_regenerate_saying(guide.status))
        if (
            guide
            and not discard_edits
            and await GuideSection.filter(guide_document=guide, edited_body__isnull=False).using_db(conn).exists()
        ):
            raise ApiError("GUIDE_HAS_EDITS", 409, "고친 문구가 있어 다시 만들지 않았습니다.")
        key = f"{actor.hospital_id}:{visit_id}"
        existing = await GuideGenerationJob.filter(active_key=key).using_db(conn).first()
        if existing:
            return existing
        return await GuideGenerationJob.create(
            visit_id=visit_id,
            hospital_id=actor.hospital_id,
            actor_id=actor.user_id,
            active_key=key,
            discard_edits=discard_edits,
            input_sha256=await input_checksum(visit_id),
            guide_version=guide.version if guide else 0,
            available_at=now(),
            using_db=conn,
        )


async def process_next_generation() -> bool:
    """Leases recover after worker crashes; the claim is fenced at final save."""
    from app.services.guides import GuideService

    async with in_transaction() as conn:
        job = (
            await GuideGenerationJob.filter(active_key__not_isnull=True, available_at__lte=now())
            .using_db(conn)
            .select_for_update(skip_locked=True)
            .order_by("available_at")
            .first()
        )
        if job is None:
            return False
        job.claim = uuid4()
        job.attempts += 1
        job.available_at = now() + timedelta(seconds=LEASE_SECONDS)
        await job.save(using_db=conn)
    try:
        staff = await Staff.filter(
            staff_id=job.actor_id, hospital_id=job.hospital_id, status=StaffStatus.ACTIVE
        ).first()
        if staff is None:
            raise GuideGenerationError("actor_unavailable")
        if job.attempts > MAX_ATTEMPTS:
            raise GuideGenerationError("retry_exhausted")
        generator = build_generator()
        actor = SimpleNamespace(user_id=staff.staff_id, hospital_id=staff.hospital_id, roles=frozenset(staff.roles))
        guide = await GuideService(rag_generator=generator, generation_job=job).generate(
            actor, job.visit_id, discard_edits=job.discard_edits
        )
        if await GuideSectionSourceSnapshot.filter(
            guide_document=guide,
            guide_version=guide.version,
            fallback_reason="search_infrastructure_exhausted",
        ).exists():
            LOGGER.error("guide_generation_degraded reason=search_infrastructure_exhausted job=%s", job.pk)
    except (GuideGenerationError, ApiError) as exc:
        await record_failure(job, exc)
    except Exception:
        await GuideGenerationJob.filter(job_id=job.pk, claim=job.claim, active_key__not_isnull=True).update(
            failure_reason="generation_internal_error",
            failed_at=now(),
            active_key=None,
        )
        LOGGER.error("guide_generation_failed reason=generation_internal_error job=%s", job.pk)
    return True
