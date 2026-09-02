"""Patient feedback submission rules for KEY-239."""

import hashlib

from tortoise.exceptions import IntegrityError
from tortoise.timezone import now

from app.core.api_errors import ApiError
from app.dtos.patient_feedback import PatientFeedbackCreateRequest
from app.models.feedback import PatientFeedback, PatientFeedbackTarget
from app.models.visits import (
    GuideDocument,
    GuideSection,
    GuideStatus,
    PatientGuideLink,
    PatientUsageEvent,
    PatientUsageEventType,
)


def _not_found() -> ApiError:
    return ApiError(404, "FEEDBACK_CONTEXT_NOT_FOUND", "피드백을 남길 안내를 찾을 수 없습니다.")


def _submission_conflict() -> ApiError:
    return ApiError(409, "FEEDBACK_SUBMISSION_CONFLICT", "같은 제출 요청에 서로 다른 내용이 포함되어 있습니다.")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PatientFeedbackService:
    """Store feedback only inside the guide selected by the patient session."""

    async def create(self, link_digest: str, data: PatientFeedbackCreateRequest) -> PatientFeedback:
        guide = await self._approved_guide(link_digest)
        usage_event_id = await self._resolve_target(guide, data)
        idempotency_digest = _digest(str(data.submission_id))

        existing = await PatientFeedback.filter(
            guide_document_id=guide.guide_document_id,
            idempotency_digest=idempotency_digest,
        ).first()
        if existing is not None:
            return self._same_or_conflict(existing, data, usage_event_id)

        try:
            return await PatientFeedback.create(
                hospital_id=guide.hospital_id,
                guide_document=guide,
                usage_event_id=usage_event_id,
                target=data.target,
                source_screen=data.source_screen,
                section_key=data.section_key,
                content_key=data.content_key,
                detected_tab=data.detected_tab,
                category=data.category,
                details=data.details,
                idempotency_digest=idempotency_digest,
            )
        except IntegrityError:
            # A network retry can race the first request. The unique constraint
            # decides the winner; the loser returns that same row only when the
            # submitted content is identical.
            existing = await PatientFeedback.get(
                guide_document_id=guide.guide_document_id,
                idempotency_digest=idempotency_digest,
            )
            return self._same_or_conflict(existing, data, usage_event_id)

    @staticmethod
    async def _approved_guide(link_digest: str) -> GuideDocument:
        link = await PatientGuideLink.filter(token_digest=link_digest).select_related("guide_document").first()
        if link is None or link.expires_at <= now():
            raise _not_found()
        guide = link.guide_document
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            raise _not_found()
        return guide

    async def _resolve_target(self, guide: GuideDocument, data: PatientFeedbackCreateRequest) -> int | None:
        if data.target is PatientFeedbackTarget.CHATBOT_RESPONSE:
            event = await PatientUsageEvent.filter(
                guide_document_id=guide.guide_document_id,
                event_type=PatientUsageEventType.CHATBOT_ANSWERED,
                response_ref_digest=_digest(data.response_ref or ""),
            ).first()
            if event is None:
                raise _not_found()
            return event.patient_usage_event_id

        section_exists = await GuideSection.filter(
            guide_document_id=guide.guide_document_id,
            section_key=data.section_key,
        ).exists()
        if not section_exists:
            raise _not_found()
        return None

    @staticmethod
    def _same_or_conflict(
        existing: PatientFeedback,
        data: PatientFeedbackCreateRequest,
        usage_event_id: int | None,
    ) -> PatientFeedback:
        same = (
            existing.usage_event_id == usage_event_id
            and existing.target == data.target
            and existing.source_screen == data.source_screen
            and existing.section_key == data.section_key
            and existing.content_key == data.content_key
            and existing.detected_tab == data.detected_tab
            and existing.category == data.category
            and existing.details == data.details
        )
        if not same:
            raise _submission_conflict()
        return existing
