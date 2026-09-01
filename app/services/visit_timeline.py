"""진료 한 건의 시간순 이력 — KEY-242 (와이어프레임 S1-4).

**사건을 새로 만들지 않는다.** 문서 업로드·OCR·안내문·D+7 체크인이 각자 자기
표에 이미 남긴 것을 병원 범위 안에서 읽어 시간순으로 합칠 뿐이다. 그래서 이
작업에는 새 모델도, 마이그레이션도 없다.

발송(문자) 사건은 여기 없다 — `SendLog` 계열 모델이 아직 없어(Sprint 5) 발송
시각을 남기는 자리 자체가 없다. 발송 이력이 생기는 일감에서 `TimelineCategory`
에 `SEND` 를 더하고 이 서비스에 한 갈래를 붙인다.

권한은 라우터의 `require_patient_read` 가 판단한다 — `PATIENT_READ` 는
staff·doctor 만 여는 권한이라 admin 단독 계정은 여기 닿지 못한다(KEY-168).
"""

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.dtos.visits import TimelineCategory, TimelineEvent, VisitTimelineEntry, VisitTimelineResponse
from app.models.documents import MedicalDocument
from app.models.ocr import OcrJob, OcrJobStatus, OcrResult
from app.models.visits import CheckIn, GuideDocument, GuideEvent, GuideEventType
from app.repositories.visit_repository import VisitRepository
from app.services.patient_visit_scope import hospital_id_of

_GUIDE_EVENT_NAME: dict[GuideEventType, TimelineEvent] = {
    GuideEventType.GENERATED: TimelineEvent.GUIDE_GENERATED,
    GuideEventType.EDITED: TimelineEvent.GUIDE_EDITED,
    GuideEventType.APPROVED: TimelineEvent.GUIDE_APPROVED,
    GuideEventType.RETURNED: TimelineEvent.GUIDE_RETURNED,
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

        entries: list[VisitTimelineEntry] = []
        entries += await self._document_entries(visit_id)
        entries += await self._ocr_entries(visit_id)
        entries += await self._guide_entries(visit_id)

        # 병원 범위는 이미 visit 로 확인했다. 각 표는 visit_id 로만 좁힌다.
        entries.sort(key=lambda entry: entry.at)
        return VisitTimelineResponse(visit_id=visit_id, entries=entries)

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
            if job.status == OcrJobStatus.COMPLETED and job.completed_at is not None:
                entries.append(
                    VisitTimelineEntry(
                        at=job.completed_at,
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

        entries: list[VisitTimelineEntry] = [
            VisitTimelineEntry(
                at=event.created_at,
                category=TimelineCategory.GUIDE,
                event=_GUIDE_EVENT_NAME[event.event_type],
                actor_id=event.actor_id,
                section_key=event.section_key,
                note=event.reason,
            )
            for event in await GuideEvent.filter(guide_document_id=guide.guide_document_id).order_by("created_at")
        ]

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
