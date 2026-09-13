"""Create an idempotent delivery job from a sent-message history row."""

from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.dtos.messages import MessageResendResponse
from app.models.visits import GuideMessage, GuideMessageStatus
from app.services.patient_links import PatientLinkService
from app.services.patient_visit_scope import hospital_id_of

RESENDABLE_STATUSES = (GuideMessageStatus.SENT, GuideMessageStatus.FAILED)


class MessageResendService:
    async def request(self, actor: ClinicalActor, message_id: int) -> MessageResendResponse:
        hospital_id = hospital_id_of(actor)

        async with in_transaction() as connection:
            source = (
                await GuideMessage.filter(
                    guide_message_id=message_id,
                    guide_document__visit__hospital_id=hospital_id,
                )
                .select_for_update()
                .using_db(connection)
                .first()
            )
            if source is None:
                raise ApiError(404, "MESSAGE_NOT_FOUND", "발송 이력을 찾을 수 없습니다.")
            if source.status not in RESENDABLE_STATUSES:
                raise ApiError(409, "MESSAGE_NOT_RESENDABLE", "완료되거나 실패한 발송만 다시 보낼 수 있습니다.")

            existing = (
                await GuideMessage.filter(resend_of_message_id=source.guide_message_id).using_db(connection).first()
            )
            if existing is not None:
                return self._response(existing)

            timestamp = now()
            await PatientLinkService().revoke_active_for_resend(
                source.guide_document_id,
                actor.staff_id,
                connection,
                timestamp,
            )
            message = await GuideMessage.create(
                guide_document_id=source.guide_document_id,
                kind=source.kind,
                status=GuideMessageStatus.SCHEDULED,
                scheduled_at=timestamp,
                resend_of_message_id=source.guide_message_id,
                resend_sequence=source.resend_sequence + 1,
                using_db=connection,
            )
            return self._response(message)

    @staticmethod
    def _response(message: GuideMessage) -> MessageResendResponse:
        return MessageResendResponse(
            guide_message_id=message.guide_message_id,
            status=message.status,
        )
