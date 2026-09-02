"""진료 한 건의 시간순 이력 — KEY-242 (와이어프레임 S1-4).

**사건을 새로 만들지 않는다.** 문서 업로드·OCR·안내문·D+7 체크인이 각자 자기
표에 이미 남긴 것을 병원 범위 안에서 읽어 시간순으로 합칠 뿐이다. 그래서 이
작업에는 새 모델도, 마이그레이션도 없다.

**두 벌이 하나가 됐다.** `#176`(KEY-234 · D1-6 현황)과 이 일감(KEY-242 · S1-4
환자 카드)이 같은 경로를 각자 만들고 있었다 — 먼저 열린 것은 이쪽인데
`#176` 이 나중에 병합되면서 `app/timeline/` 이 develop 에 들어갔다. 중복을
만든 것은 `#176` 쪽이다.

**어느 쪽도 다른 쪽의 상위집합이 아니었다.** 각자 상대가 안 읽는 표를 셋씩
갖고 있어서, 하나를 지우면 진짜 기능이 사라진다.

    문서 업로드 · 판독 시작/완료/실패/확정      KEY-242 만 읽던 것
    진료 열림 · 환자 열람 · 나갈 문자          KEY-234 만 읽던 것
    안내문 사건 · 체크인                       둘 다

어휘(`TimelineEvent`·`TimelineCategory`)는 이쪽 것을 쓴다 — 저쪽은 `kind: str`
이라 오타가 조용히 지난다. 사람 이름과 `messages` 는 저쪽 것을 가져왔다.

발송 **이력**(언제 실제로 나갔나)은 아직 없다 — `SendLog` 계열 모델이 없어서
(Sprint 5) 발송 시각을 남기는 자리가 없다. `messages` 는 **예약**이라 다르다:
`guide_message` 에 이미 있는 「언제 나갈 것인가」를 읽는다.

권한은 라우터의 `require_patient_read` 가 판단한다 — `PATIENT_READ` 는
staff·doctor 만 여는 권한이라 admin 단독 계정은 여기 닿지 못한다(KEY-168).
"""

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.dtos.visits import (
    ScheduledMessage,
    TimelineCategory,
    TimelineEvent,
    VisitTimelineEntry,
    VisitTimelineResponse,
)
from app.models.documents import MedicalDocument
from app.models.ocr import OcrJob, OcrJobStatus, OcrResult
from app.models.staffs import Staff
from app.models.visits import (
    CheckIn,
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideMessage,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
from app.repositories.visit_repository import VisitRepository
from app.services.patient_visit_scope import hospital_id_of

_GUIDE_EVENT_NAME: dict[GuideEventType, TimelineEvent] = {
    GuideEventType.GENERATED: TimelineEvent.GUIDE_GENERATED,
    GuideEventType.EDITED: TimelineEvent.GUIDE_EDITED,
    GuideEventType.SUBMITTED: TimelineEvent.GUIDE_SUBMITTED,
    GuideEventType.APPROVED: TimelineEvent.GUIDE_APPROVED,
    GuideEventType.UNAPPROVED: TimelineEvent.GUIDE_UNAPPROVED,
    GuideEventType.RETURNED: TimelineEvent.GUIDE_RETURNED,
}

_PATIENT_EVENT_NAME: dict[PatientUsageEventType, TimelineEvent] = {
    PatientUsageEventType.GUIDE_VIEWED: TimelineEvent.GUIDE_VIEWED,
    PatientUsageEventType.CHATBOT_ANSWERED: TimelineEvent.CHATBOT_ANSWERED,
}


class VisitTimelineService:
    def __init__(self) -> None:
        self.repo = VisitRepository()

    async def timeline(self, actor: ClinicalActor, visit_id: int) -> VisitTimelineResponse:
        hospital_id = hospital_id_of(actor)
        visit = await self.repo.get_scoped(visit_id, hospital_id)
        if visit is None:
            # 다른 병원 진료도 같은 응답을 준다 — 리소스가 있는지 없는지를
            # 상태 코드로 구분해 노출하지 않는다.
            raise ApiError(404, "VISIT_NOT_FOUND", "진료를 찾을 수 없습니다.")

        # 병원 범위는 이미 visit 로 확인했다. 각 표는 visit_id 로만 좁힌다.
        entries: list[VisitTimelineEntry] = [self._visit_entry(visit)]
        entries += await self._document_entries(visit_id)
        entries += await self._ocr_entries(visit_id)
        entries += await self._guide_entries(visit_id)
        entries += await self._patient_entries(visit_id)

        # **오래된 것이 위다.** 진료가 어떻게 흘러갔는지 읽는 자리라, 최신순
        # 으로 뒤집으면 거꾸로 읽게 된다. 파이썬 정렬은 안정 정렬이라 `at` 이
        # 같은 사건은 위에서 더한 차례(진료 → 문서 → 판독 → 안내문 → 환자)로
        # 남는다 — 씨앗 데이터처럼 시각이 겹칠 때 그 차례가 자연스럽다.
        entries.sort(key=lambda entry: entry.at)
        return VisitTimelineResponse(
            visit_id=visit_id,
            entries=await self._named(entries),
            messages=await self._messages(visit_id),
        )

    @staticmethod
    def _visit_entry(visit: Visit) -> VisitTimelineEntry:
        """진료가 열린 것. **이력의 첫 줄이다** — 이것이 없으면 이력이 문서
        업로드부터 시작해서, 진료를 등록만 하고 아무것도 안 한 환자의 화면이
        통째로 빈다."""
        return VisitTimelineEntry(
            at=visit.visited_at,
            category=TimelineCategory.VISIT,
            event=TimelineEvent.VISIT_CREATED,
            actor_id=visit.doctor_id,
        )

    @staticmethod
    async def _named(entries: list[VisitTimelineEntry]) -> list[VisitTimelineEntry]:
        """번호에 이름을 붙인다.

        **한 번에 모아 온다.** 줄마다 물어보면 스무 줄에 스무 번 간다. 화면이
        번호를 받아 다시 물으면 같은 왕복이 브라우저에서 일어난다.
        """
        wanted = {entry.actor_id for entry in entries if entry.actor_id is not None}
        if not wanted:
            return entries
        names = {staff.staff_id: staff.name for staff in await Staff.filter(staff_id__in=list(wanted))}
        for entry in entries:
            if entry.actor_id is not None:
                entry.actor = names.get(entry.actor_id)
        return entries

    @staticmethod
    async def _patient_entries(visit_id: int) -> list[VisitTimelineEntry]:
        """환자가 한 일 — 열람 · 챗봇. **행위자는 비운다**(환자다).

        `grounded_section` 이 있는 열람만 그 장을 읽은 것으로 본다. 없는 것은
        「열었다」까지다.
        """
        guide = await GuideDocument.get_or_none(visit_id=visit_id)
        if guide is None:
            return []
        found = []
        for used in await PatientUsageEvent.filter(guide_document_id=guide.guide_document_id).order_by("created_at"):
            name = _PATIENT_EVENT_NAME.get(used.event_type)
            if name is None:
                # 모르는 사건은 건너뛴다 — 한 줄 때문에 화면이 죽지 않는다.
                continue
            found.append(
                VisitTimelineEntry(
                    at=used.created_at,
                    category=TimelineCategory.PATIENT,
                    event=name,
                    section_key=used.grounded_section or None,
                )
            )
        return found

    @staticmethod
    async def _messages(visit_id: int) -> list[ScheduledMessage]:
        """나갈 문자 — **예정 시각 순**이다.

        만든 차례로 두면 소진 임박이 확인 회차보다 위에 뜬다(먼저 만들어질 수
        있어서). 승인 전에는 비어 있다 — 예약은 승인이 만든다.
        """
        guide = await GuideDocument.get_or_none(visit_id=visit_id)
        if guide is None:
            return []
        return [
            ScheduledMessage(
                kind=str(row.kind),
                status=str(row.status),
                at=row.scheduled_at,
                sent_at=row.sent_at,
                failure_code=row.failure_code,
                hold_reason=row.hold_reason,
            )
            for row in await GuideMessage.filter(guide_document_id=guide.guide_document_id).order_by("scheduled_at")
        ]

    @staticmethod
    async def _document_entries(visit_id: int) -> list[VisitTimelineEntry]:
        return [
            VisitTimelineEntry(
                at=document.created_at,
                category=TimelineCategory.DOCUMENT,
                event=TimelineEvent.DOCUMENT_UPLOADED,
                actor_id=document.uploaded_by,
                document_type=document.document_type,
            )
            for document in await MedicalDocument.filter(visit_id=visit_id).order_by("created_at")
        ]

    @staticmethod
    async def _ocr_entries(visit_id: int) -> list[VisitTimelineEntry]:
        jobs = await OcrJob.filter(visit_id=visit_id).order_by("created_at")
        entries: list[VisitTimelineEntry] = []
        for job in jobs:
            entries.append(
                VisitTimelineEntry(
                    at=job.created_at,
                    category=TimelineCategory.OCR,
                    event=TimelineEvent.OCR_STARTED,
                    actor_id=job.requested_by,
                )
            )
            if job.status == OcrJobStatus.COMPLETED:
                # `completed_at` 은 `null=True` 다. 실패 쪽만 `updated_at` 으로
                # 대비하고 완료 쪽은 안 하고 있었는데, 그러면 상태만 바뀌고
                # 시각이 안 채워진 작업은 이력에 `OCR_STARTED` 만 남아
                # **스탭이 판독이 아직 도는 중으로 읽는다.** 같은 값의 결측을
                # 두 가지로 다루면 한쪽을 고칠 때 다른 쪽을 놓친다.
                entries.append(
                    VisitTimelineEntry(
                        at=job.completed_at or job.updated_at,
                        category=TimelineCategory.OCR,
                        event=TimelineEvent.OCR_COMPLETED,
                    )
                )
            elif job.status == OcrJobStatus.FAILED:
                entries.append(
                    VisitTimelineEntry(
                        at=job.completed_at or job.updated_at,
                        category=TimelineCategory.OCR,
                        event=TimelineEvent.OCR_FAILED,
                        note=job.failure_code,
                    )
                )

        job_ids = [job.ocr_job_id for job in jobs]
        if job_ids:
            confirmed = (
                await OcrResult.filter(ocr_job_id__in=job_ids)
                .filter(confirmed_at__isnull=False)
                .order_by("confirmed_at")
            )
            entries += [
                VisitTimelineEntry(
                    at=result.confirmed_at,
                    category=TimelineCategory.OCR,
                    event=TimelineEvent.OCR_CONFIRMED,
                    actor_id=result.confirmed_by,
                )
                for result in confirmed
                if result.confirmed_at is not None
            ]
        return entries

    @staticmethod
    async def _guide_entries(visit_id: int) -> list[VisitTimelineEntry]:
        guide = await GuideDocument.get_or_none(visit_id=visit_id)
        if guide is None:
            return []

        entries: list[VisitTimelineEntry] = []
        for event in await GuideEvent.filter(guide_document_id=guide.guide_document_id).order_by("created_at"):
            name = _GUIDE_EVENT_NAME.get(event.event_type)
            if name is None:
                # **모르는 사건은 건너뛴다.** 사전을 `[]` 로 꺼내고 있었는데,
                # 그러면 `GuideEventType` 에 값이 하나 늘 때마다 이 화면이
                # 통째로 500 이 된다. 실제로 `SUBMITTED`·`UNAPPROVED` 가
                # `#176` 으로 늘었고, 제출은 승인 앞에 필수라 거의 모든
                # 안내문에 남는다 — 드문 경우가 아니었다.
                continue
            entries.append(
                VisitTimelineEntry(
                    at=event.created_at,
                    category=TimelineCategory.GUIDE,
                    event=name,
                    actor_id=event.actor_id,
                    section_key=event.section_key,
                    note=event.reason,
                )
            )

        check_in = await CheckIn.get_or_none(guide_document_id=guide.guide_document_id)
        if check_in is not None:
            entries.append(
                VisitTimelineEntry(
                    at=check_in.created_at,
                    category=TimelineCategory.CHECK_IN,
                    event=TimelineEvent.CHECK_IN_SUBMITTED,
                )
            )
        return entries
