"""KEY-238: 선택 이력은 append-only, 현재 상태와 확인 사실은 별도 보관한다."""

from tortoise.transactions import in_transaction

from app.core.auth_errors import AuthError as ApiError
from app.dtos.checkins import CheckInCreateRequest, CheckInSignalRequest, SignalAcknowledgeRequest
from app.models.visits import (
    CheckIn,
    CheckInMedication,
    CheckInSignal,
    CheckInSignalAcknowledgement,
    CheckInSignalState,
    GuideDocument,
    Visit,
)
from app.services.patient_links import PatientLinkService

REVIEW_ANSWERS = frozenset({CheckInMedication.STOPPED_SIDE_EFFECT, CheckInMedication.STOPPED_IMPROVED})


class CheckInSignalService:
    def __init__(self, links: PatientLinkService | None = None) -> None:
        self.links = links or PatientLinkService()

    async def lock_guide(self, token: str) -> GuideDocument:
        _, guide = await self.links.get_approved_guide(token)
        await GuideDocument.filter(pk=guide.pk).select_for_update().get()
        _, guide = await self.links.get_approved_guide(token)
        return guide

    @staticmethod
    async def set_current(guide, state, answer, client_id, sequence, signal_id) -> CheckInSignalState:
        changed = state is None or state.answer_key != answer
        if state is None:
            state = CheckInSignalState(guide_document=guide, answer_key=answer)
        state.answer_key = answer
        state.client_id = client_id
        state.client_sequence = sequence
        state.signal_id = signal_id
        state.needs_review = answer in REVIEW_ANSWERS
        if changed:
            state.acknowledged_by = None
            state.acknowledged_at = None
        await state.save()
        return state

    async def correct_from_save(self, guide: GuideDocument, payload: CheckInCreateRequest) -> None:
        state = await CheckInSignalState.filter(guide_document_id=guide.pk).select_for_update().first()
        await self.set_current(guide, state, payload.medication, payload.client_id, payload.client_sequence, None)

    async def signal(self, token: str, payload: CheckInSignalRequest) -> tuple[CheckInSignal, CheckInSignalState, bool]:
        async with in_transaction():
            guide = await self.lock_guide(token)
            # MySQL REPEATABLE READ의 잠금 전 snapshot을 재사용하지 않는다.
            state = await CheckInSignalState.filter(guide_document_id=guide.pk).select_for_update().first()
            event = (
                await CheckInSignal.filter(
                    guide_document_id=guide.pk, client_id=payload.client_id, client_sequence=payload.client_sequence
                )
                .select_for_update()
                .first()
            )
            if event is not None:
                if event.answer_key != payload.answer_key or event.client_session_id != payload.client_session_id:
                    raise ApiError("CHECKIN_SIGNAL_CONFLICT", 409, "이미 사용한 신호 순번입니다.")
                if state is None:
                    raise RuntimeError("signal state is missing")
                return event, state, state.signal_id == event.pk
            event = await CheckInSignal.create(guide_document=guide, **payload.model_dump())
            current = (
                state is None
                or state.client_id != payload.client_id
                or (state.client_sequence is None or payload.client_sequence > state.client_sequence)
            )
            saved = await CheckIn.filter(guide_document_id=guide.pk).select_for_update().first()
            if saved is not None:
                # 최종 저장 뒤 늦게 도착한 선택은 이력에만 남긴다.
                current = False
                if state is None:
                    state = await self.set_current(guide, None, saved.medication, None, None, None)
            elif current:
                state = await self.set_current(
                    guide, state, payload.answer_key, payload.client_id, payload.client_sequence, event.pk
                )
            if state is None:
                raise RuntimeError("signal state is missing")
            return event, state, current

    @staticmethod
    def check_role(actor) -> None:
        if not {"staff", "doctor"}.intersection(actor.roles):
            raise ApiError("FORBIDDEN", 403, "D+7 신호를 조회할 권한이 없습니다.")

    async def read(self, actor, visit_id: int) -> list[CheckInSignalState]:
        self.check_role(actor)
        if not await Visit.filter(pk=visit_id, hospital_id=actor.hospital_id).exists():
            raise ApiError("CHECKIN_NOT_FOUND", 404, "D+7 응답을 찾을 수 없습니다.")
        return await CheckInSignalState.filter(
            guide_document__visit_id=visit_id, guide_document__visit__hospital_id=actor.hospital_id
        ).order_by("-updated_at", "-state_id")

    async def acknowledge(
        self, actor, visit_id: int, state_id: int, payload: SignalAcknowledgeRequest
    ) -> CheckInSignalState:
        self.check_role(actor)
        async with in_transaction():
            state = await CheckInSignalState.filter(
                pk=state_id,
                guide_document__visit_id=visit_id,
                guide_document__visit__hospital_id=actor.hospital_id,
            ).first()
            if state is None:
                raise ApiError("CHECKIN_NOT_FOUND", 404, "D+7 응답을 찾을 수 없습니다.")
            await GuideDocument.filter(pk=state.guide_document_id).select_for_update().get()
            state = await CheckInSignalState.filter(pk=state_id).select_for_update().get()
            if state.signal_id != payload.signal_id or state.updated_at != payload.updated_at:
                raise ApiError("CHECKIN_SIGNAL_CHANGED", 409, "선택 내용이 바뀌었습니다. 다시 확인해 주세요.")
            if not state.needs_review:
                raise ApiError("CHECKIN_SIGNAL_NOT_REVIEWABLE", 409, "확인 대상 신호가 아닙니다.")
            if state.acknowledged_at is None:
                ack = await CheckInSignalAcknowledgement.create(state=state, actor_id=actor.user_id)
                state.acknowledged_by = actor.user_id
                state.acknowledged_at = ack.created_at
                await state.save()
            return state
