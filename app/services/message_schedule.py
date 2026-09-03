"""발송 예정 목록 — 와이어프레임 S2-3.

**두 규칙이 이 화면의 전부다.**

1. **안 나간 것은 창 밖이어도 보인다.** 실패·보류는 기간을 좁혔다고 사라지면
   안 된다 — 원문에서 박수빈의 08-11 실패는 지난 것이고 강예린의 11-06 보류는
   「앞으로 7일」 밖인데 둘 다 떠 있다. 놓치면 환자가 문자를 못 받는다.
2. **예정은 고른 기간 안의 것만.** 이쪽은 훑어보는 것이라 창이 뜻이 있다.

두 규칙을 한 질의로 합치지 않는다. 합치려면 「상태가 이것이면 창을 무시」를
SQL 안에 넣게 되는데, 그러면 읽는 사람이 창의 뜻을 오해한다.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tortoise.timezone import now

from app.core.api_errors import ApiError
from app.core.time import clinic_day_window
from app.dependencies.patient_access import ClinicalActor
from app.dtos.messages import (
    MessagePatchRequest,
    MessagePatchResponse,
    ScheduledMessageCounts,
    ScheduledMessageItem,
)
from app.dtos.patients import calculate_age
from app.models.prescriptions import Prescription
from app.models.visits import GuideMessage, GuideMessageStatus
from app.services.patient_visit_scope import hospital_id_of

#: 안 나간 것 — 이 화면이 맨 위에 올리는 무더기.
UNSENT = (GuideMessageStatus.FAILED, GuideMessageStatus.HELD)


@dataclass(frozen=True, slots=True)
class ScheduledMessagePage:
    items: list[ScheduledMessageItem]
    counts: ScheduledMessageCounts
    truncated: bool


def sort_key(status: GuideMessageStatus, scheduled_at: datetime) -> tuple[int, datetime]:
    """**안 나간 것이 먼저, 그 안에서는 시각순.**

    실패와 보류를 다시 가르지 않는다. 요약 줄이 「안 나간 것 3건 (실패 1 ·
    보류 2)」으로 한 무더기를 먼저 말하고 괄호로 쪼개는데, 표도 같은 순서로
    읽히는 편이 낫다 — 위에서부터 손대면 되는 차례가 된다.
    """
    return (0 if status in UNSENT else 1, scheduled_at)


class MessageScheduleService:
    async def list_scheduled(
        self,
        actor: ClinicalActor,
        *,
        days: int,
        today: date,
        limit: int,
    ) -> ScheduledMessagePage:
        hospital_id = hospital_id_of(actor)

        day_start, day_end = clinic_day_window(today)
        window_end = day_start + timedelta(days=days)

        rows = await self._rows(hospital_id)
        unsent = [row for row in rows if row.status in UNSENT]
        scheduled = [row for row in rows if row.status is GuideMessageStatus.SCHEDULED]
        in_window = [row for row in scheduled if day_start <= row.scheduled_at < window_end]

        counts = ScheduledMessageCounts(
            total=len(rows),
            failed=sum(1 for row in rows if row.status is GuideMessageStatus.FAILED),
            held=sum(1 for row in rows if row.status is GuideMessageStatus.HELD),
            today=sum(1 for row in scheduled if day_start <= row.scheduled_at < day_end),
            window=len(in_window),
        )

        shown = sorted(
            unsent + in_window[:limit],
            key=lambda row: sort_key(row.status, row.scheduled_at),
        )
        return ScheduledMessagePage(
            items=await self._items(shown, today),
            counts=counts,
            truncated=len(in_window) > limit,
        )

    async def update_message(
        self,
        actor: ClinicalActor,
        message_id: int,
        payload: MessagePatchRequest,
    ) -> MessagePatchResponse:
        hospital_id = hospital_id_of(actor)

        message = await GuideMessage.filter(
            guide_message_id=message_id,
            guide_document__visit__hospital_id=hospital_id,
        ).first()

        if message is None:
            raise ApiError(
                404,
                "NOT_FOUND",
                "예약 문자를 찾을 수 없습니다.",
            )

        if message.status is not GuideMessageStatus.SCHEDULED:
            raise ApiError(
                409,
                "MESSAGE_NOT_EDITABLE",
                "발송 예정 상태의 문자만 변경할 수 있습니다.",
            )

        updates: dict[str, object] = {
            "updated_at": now(),
        }

        if payload.scheduled_at is not None:
            updates["scheduled_at"] = payload.scheduled_at
            response_scheduled_at = payload.scheduled_at
            response_status = GuideMessageStatus.SCHEDULED
        else:
            updates["status"] = GuideMessageStatus.CANCELED
            response_scheduled_at = message.scheduled_at
            response_status = GuideMessageStatus.CANCELED

        affected = await GuideMessage.filter(
            guide_message_id=message_id,
            status=GuideMessageStatus.SCHEDULED,
        ).update(**updates)

        if affected != 1:
            raise ApiError(
                409,
                "MESSAGE_NOT_EDITABLE",
                "이미 발송되었거나 상태가 변경된 문자입니다.",
            )

        return MessagePatchResponse(
            guide_message_id=message.guide_message_id,
            scheduled_at=response_scheduled_at,
            status=response_status,
        )

    @staticmethod
    async def _rows(hospital_id: int) -> list[GuideMessage]:
        """**의원 격리는 `visit` 을 타고 판단한다.**

        `guide_document` 에도 `hospital_id` 사본이 있지만 그것은 목록을 거르는
        인덱스용이고, 격리 판정에 쓰지 않는 것이 이 저장소의 규칙이다
        (`GuideService.get()` 과 같다). 같은 값을 두 곳에 두면 어긋날 자리도
        함께 생기고, 어긋난 순간 남의 의원 것이 열린다.
        """
        return await (
            GuideMessage.filter(
                status__in=[*UNSENT, GuideMessageStatus.SCHEDULED],
                guide_document__visit__hospital_id=hospital_id,
            )
            .prefetch_related("guide_document__visit__patient")
            .order_by("scheduled_at", "guide_message_id")
        )

    @staticmethod
    async def _items(rows: list[GuideMessage], today: date) -> list[ScheduledMessageItem]:
        sets = await MessageScheduleService._sets([row.guide_document.visit_id for row in rows])
        items = []
        for row in rows:
            visit = row.guide_document.visit
            patient = visit.patient
            items.append(
                ScheduledMessageItem(
                    guide_message_id=row.guide_message_id,
                    visit_id=visit.visit_id,
                    patient_id=patient.patient_id,
                    scheduled_at=row.scheduled_at,
                    kind=row.kind,
                    status=row.status,
                    hold_reason=row.hold_reason,
                    failure_code=row.failure_code,
                    name=patient.name,
                    hospital_patient_no=patient.hospital_patient_no,
                    gender=patient.gender,
                    birth_date=patient.birth_date,
                    age=calculate_age(patient.birth_date, as_of=today),
                    prescription_set=sets.get(visit.visit_id),
                )
            )
        return items

    @staticmethod
    async def _sets(visit_ids: list[int]) -> dict[int, str]:
        """세트명은 **그때 남긴 스냅샷**이다 (`Prescription.prescription_set`).

        처방 세트 표(`prescription_set`)를 조인하지 않는다. 세트가 개정돼도 그
        진료가 무엇을 근거로 했는지는 바뀌면 안 되기 때문이다.
        """
        if not visit_ids:
            return {}
        rows = await Prescription.filter(visit_id__in=visit_ids).values_list("visit_id", "prescription_set")
        return {visit_id: name for visit_id, name in rows}
