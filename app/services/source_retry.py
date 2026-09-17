"""Authorized, versioned recovery requests; never deletes or sends from HTTP."""

from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.dtos.messages import SourceRetryResponse
from app.models.visits import (
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageHold,
    GuideMessageStatus,
)
from app.services.patient_visit_scope import hospital_id_of


class SourceRetryService:
    async def request(self, actor: ClinicalActor, message_id: int, generation: int) -> SourceRetryResponse:
        async with in_transaction() as connection:
            message = (
                await GuideMessage.filter(
                    guide_message_id=message_id,
                    guide_document__visit__hospital_id=hospital_id_of(actor),
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if message is None:
                raise ApiError(404, "MESSAGE_NOT_FOUND", "문자를 찾을 수 없습니다.")
            # An old request is acknowledged, never re-executed after a failed attempt.
            if generation < message.source_retry_generation:
                return self.response(message)
            if generation != message.source_retry_generation or (
                message.status != GuideMessageStatus.HELD
                or message.hold_reason != GuideMessageHold.SOURCE_NOT_DELETED
                or message.claim_token is not None
            ):
                raise ApiError(409, "SOURCE_RETRY_NOT_ALLOWED", "원본 삭제 보류 상태를 새로 확인해 주세요.")
            if not message.source_retry_requested:
                message.source_retry_requested = True
                message.source_retry_generation += 1
                await message.save(
                    using_db=connection, update_fields=["source_retry_requested", "source_retry_generation"]
                )
                await GuideMessageEvent.create(
                    guide_message_id=message_id,
                    event_type=GuideMessageEventType.SOURCE_RETRY,
                    reason=f"staff_id={actor.staff_id};generation={message.source_retry_generation}",
                    using_db=connection,
                )
            return self.response(message)

    @staticmethod
    def response(message: GuideMessage) -> SourceRetryResponse:
        return SourceRetryResponse(
            guide_message_id=message.guide_message_id,
            status=message.status,
            source_retry_requested=message.source_retry_requested,
            source_retry_generation=message.source_retry_generation,
        )
