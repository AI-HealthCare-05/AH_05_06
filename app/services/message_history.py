"""발송 이력 — 와이어프레임 S2-4.

원문 캡션: 「기간으로 본다 · 실패 건은 맨 위에 고정」. 설계 주석이 왜인지도
적는다 — 「실패 건은 목록에 섞이면 묻히므로 맨 위에 따로 고정한다.」

발송 예정(S2-3)과 **묻는 것이 다르다.** 저쪽은 「앞으로 무엇이 나가나」이고
이쪽은 「무엇이 나갔나」다. 그래서 창도 다르다 — 저쪽은 앞으로 며칠이고
이쪽은 지난 기간의 시작과 끝이다.

원문의 견본 세 줄에서는 고정 표시가 실패 줄이 아니라 완료 줄에 붙어 있는데,
캡션과 설계 주석이 둘 다 「실패가 맨 위」라고 못박으므로 적힌 규칙을 따랐다.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tortoise.expressions import Q

from app.core.api_errors import ApiError
from app.core.time import clinic_day_window
from app.dependencies.patient_access import ClinicalActor
from app.dtos.messages import SentMessageCounts, SentMessageItem
from app.dtos.patients import calculate_age
from app.models.prescriptions import Prescription
from app.models.visits import (
    GuideMessage,
    GuideMessageStatus,
    PatientUsageEvent,
    PatientUsageEventType,
)
from app.services.patient_visit_scope import hospital_id_of

#: 지난 일 — 이 화면이 담는 것.
HAPPENED = (GuideMessageStatus.SENT, GuideMessageStatus.FAILED)

#: 한 번에 훑을 수 있는 가장 긴 기간. 넘겨 받으면 막는다 — 조용히 줄이면
#: 화면이 「1년치를 봤다」고 믿는다.
MAX_DAYS = 366


def happened_at(message: GuideMessage) -> datetime:
    """**보낸 시각이 없으면 예정이었던 시각.**

    못 나간 줄에는 `sent_at` 이 없는데 원문은 실패 줄에도 시각을 적는다 —
    「언제 일이 있었나」를 묻는 칸이지 「언제 나갔나」만 묻는 칸이 아니다.
    """
    return message.sent_at or message.scheduled_at


def sort_key(status: GuideMessageStatus, at: datetime) -> tuple[int, float]:
    """**실패가 맨 위, 그 다음 최신순.**

    이력은 최신이 위다 — 방금 무슨 일이 있었나를 먼저 묻는다. 발송
    예정(S2-3)이 시각 오름차순인 것과 반대이고, 그래야 각 화면이 묻는 것과
    맞는다.
    """
    return (0 if status is GuideMessageStatus.FAILED else 1, -at.timestamp())


@dataclass(frozen=True, slots=True)
class SentMessagePage:
    items: list[SentMessageItem]
    counts: SentMessageCounts
    truncated: bool


class MessageHistoryService:
    async def list_sent(
        self,
        actor: ClinicalActor,
        *,
        since: date,
        until: date,
        limit: int | None,
    ) -> SentMessagePage:
        hospital_id = hospital_id_of(actor)
        self._check_range(since, until)

        start, _ = clinic_day_window(since)
        _, end = clinic_day_window(until)

        rows = await self._rows(hospital_id, start, end)
        failed = [row for row in rows if row.status is GuideMessageStatus.FAILED]
        sent = [row for row in rows if row.status is GuideMessageStatus.SENT]

        viewed = await self._viewed({row.guide_document_id for row in rows})
        counts = SentMessageCounts(
            total=len(rows),
            failed=len(failed),
            viewed=sum(1 for row in sent if row.guide_document_id in viewed),
            unviewed=sum(1 for row in sent if row.guide_document_id not in viewed),
        )

        # **실패는 잘리지 않는다.** 이 화면이 맨 위에 고정하라고 한 것을
        # 잘라 내면 고정할 까닭이 없어진다.
        shown = failed + (sent if limit is None else sent[:limit])
        shown.sort(key=lambda row: sort_key(row.status, happened_at(row)))

        return SentMessagePage(
            items=await self._items(shown, viewed, until),
            counts=counts,
            truncated=limit is not None and len(sent) > limit,
        )

    @staticmethod
    def _check_range(since: date, until: date) -> None:
        if until < since:
            raise ApiError(400, "INVALID_RANGE", "기간의 끝이 시작보다 앞설 수 없습니다.")
        if (until - since) >= timedelta(days=MAX_DAYS):
            raise ApiError(400, "RANGE_TOO_LONG", f"한 번에 볼 수 있는 기간은 {MAX_DAYS}일까지입니다.")

    @staticmethod
    async def _rows(hospital_id: int, start: datetime, end: datetime) -> list[GuideMessage]:
        """**격리는 `visit` 을 타고 판단한다** — `guide_document.hospital_id` 는
        목록을 거르는 인덱스용 사본이라 격리 판정에 쓰지 않는다.

        시각은 `sent_at` 이 있으면 그것, 없으면 `scheduled_at` 으로 거른다.
        한 칸으로 합쳐 두면 편하겠지만, 나간 시각과 예정이었던 시각은 다른
        것이라 합칠 수 없다.
        """
        when = Q(sent_at__gte=start, sent_at__lt=end) | Q(
            sent_at__isnull=True, scheduled_at__gte=start, scheduled_at__lt=end
        )
        return await (
            GuideMessage.filter(status__in=HAPPENED, guide_document__visit__hospital_id=hospital_id)
            .filter(when)
            .prefetch_related("guide_document__visit__patient")
            .order_by("-scheduled_at", "-guide_message_id")
        )

    @staticmethod
    async def _viewed(document_ids: set[int]) -> dict[int, datetime]:
        """열람은 **안내문 단위**다 — 링크 하나가 안내문 하나를 연다.

        어느 문자를 보고 열었는지는 물을 수 없다. 문자 다섯 통이 같은 안내문을
        가리키므로, 한 번 열면 다섯 줄이 다 열람으로 뜬다. 그게 맞는 답이다 —
        「이 환자가 이 안내를 봤나」가 물음이지 「어느 문자가 효과가 있었나」가
        아니다.
        """
        if not document_ids:
            return {}
        rows = await PatientUsageEvent.filter(
            guide_document_id__in=document_ids,
            event_type=PatientUsageEventType.GUIDE_VIEWED,
        ).values_list("guide_document_id", "created_at")
        first: dict[int, datetime] = {}
        for document_id, at in rows:
            if document_id not in first or at < first[document_id]:
                first[document_id] = at
        return first

    @staticmethod
    async def _items(
        rows: list[GuideMessage],
        viewed: dict[int, datetime],
        as_of: date,
    ) -> list[SentMessageItem]:
        sets = await MessageHistoryService._sets([row.guide_document.visit_id for row in rows])
        items = []
        for row in rows:
            visit = row.guide_document.visit
            patient = visit.patient
            items.append(
                SentMessageItem(
                    guide_message_id=row.guide_message_id,
                    visit_id=visit.visit_id,
                    patient_id=patient.patient_id,
                    happened_at=happened_at(row),
                    kind=row.kind,
                    status=row.status,
                    failure_code=row.failure_code,
                    name=patient.name,
                    hospital_patient_no=patient.hospital_patient_no,
                    gender=patient.gender,
                    birth_date=patient.birth_date,
                    age=calculate_age(patient.birth_date, as_of=as_of),
                    prescription_set=sets.get(visit.visit_id),
                    viewed=row.guide_document_id in viewed,
                    viewed_at=viewed.get(row.guide_document_id),
                )
            )
        return items

    @staticmethod
    async def _sets(visit_ids: list[int]) -> dict[int, str]:
        if not visit_ids:
            return {}
        rows = await Prescription.filter(visit_id__in=visit_ids).values_list("visit_id", "prescription_set")
        return {visit_id: name for visit_id, name in rows}
