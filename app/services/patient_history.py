"""환자 이력 — 와이어프레임 S2-2.

**환자 단위다.** 이미 있는 진료 타임라인(`app/timeline`)은 진료 하나짜리라,
「이 환자가 지난 세 번 어떻게 했나」를 물을 수 없었다. 그 화면(D1-6)과 묻는
것이 다르다 — 저쪽은 「이 진료가 어떻게 흘러갔나」이고 이쪽은 「이 환자가
계속 하고 있나」다.

원문 캡션: 「S2-1 위에 뜬다 · 스탭 · 의사 공통」.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.dtos.patient_history import HistoryCheck, HistoryVisit
from app.models.ocr import OcrField
from app.models.patients import Patient
from app.models.prescriptions import Prescription
from app.models.staffs import Staff
from app.models.visits import (
    CheckIn,
    GuideDocument,
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
from app.services.patient_flags import CHECK_KINDS
from app.services.patient_visit_scope import hospital_id_of

#: 원문이 세 블록을 보인다 — 「지난 안내문 4건 중 3건」. 모달이 800px 이라
#: 그 이상은 어차피 스크롤이고, 나머지가 몇 건인지는 아래 줄이 말한다.
DEFAULT_VISITS = 3


@dataclass(frozen=True, slots=True)
class PatientHistory:
    patient: Patient
    doctor: Staff | None
    diagnosis_name: str | None
    visits: list[HistoryVisit]
    total: int


class PatientHistoryService:
    async def read(self, actor: ClinicalActor, patient_id: int, *, limit: int) -> PatientHistory:
        hospital_id = hospital_id_of(actor)
        patient = await Patient.get_or_none(patient_id=patient_id, hospital_id=hospital_id)
        if patient is None:
            # 남의 의원 것은 **없는 것이다.** 있고 없고가 새면 그 자체가 정보다.
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")

        every = await Visit.filter(patient_id=patient_id, hospital_id=hospital_id).order_by("-visited_at")
        shown = every[:limit]
        visit_ids = [visit.visit_id for visit in shown]

        documents = {row.visit_id: row for row in await GuideDocument.filter(visit_id__in=visit_ids)}
        messages = await self._messages(list(documents.values()))
        views = await self._views(list(documents.values()))
        answers = await self._answers(list(documents.values()))
        courses = await self._courses(visit_ids)

        newest = every[0].visited_at if every else None
        blocks = []
        for visit in shown:
            document = documents.get(visit.visit_id)
            document_id = document.guide_document_id if document else None
            sent = messages.get(document_id, {})
            course = courses.get(visit.visit_id)
            blocks.append(
                HistoryVisit(
                    visit_id=visit.visit_id,
                    visited_at=visit.visited_at,
                    prescription_set=course[0] if course else None,
                    course_days=course[1] if course else None,
                    guide_sent_at=self._guide_sent(sent),
                    guide_viewed_at=self._first(views.get(document_id, [])),
                    checks=self._checks(sent, views.get(document_id, []), answers.get(document_id)),
                    runs_out_on=self._runs_out(visit.visited_at.date(), course),
                    revisited=newest is not None and visit.visited_at < newest,
                )
            )

        return PatientHistory(
            patient=patient,
            doctor=await self._doctor(shown, hospital_id),
            diagnosis_name=await self._diagnosis(visit_ids, hospital_id),
            visits=blocks,
            total=len(every),
        )

    # ── 모아 읽기 ────────────────────────────────────────
    #
    # 진료마다 한 번씩 물으면 세 블록에 열다섯 번 간다. 지금은 셋뿐이지만
    # `limit` 를 늘리는 날 그대로 늘어난다.

    @staticmethod
    async def _messages(documents: list[GuideDocument]) -> dict[int, dict[str, GuideMessage]]:
        if not documents:
            return {}
        rows = await GuideMessage.filter(guide_document_id__in=[row.guide_document_id for row in documents]).order_by(
            "scheduled_at"
        )
        found: dict[int, dict[str, GuideMessage]] = {}
        for row in rows:
            found.setdefault(row.guide_document_id, {})[str(row.kind)] = row
        return found

    @staticmethod
    async def _views(documents: list[GuideDocument]) -> dict[int, list[datetime]]:
        if not documents:
            return {}
        rows = await PatientUsageEvent.filter(
            guide_document_id__in=[row.guide_document_id for row in documents],
            event_type=PatientUsageEventType.GUIDE_VIEWED,
        ).values_list("guide_document_id", "created_at")
        found: dict[int, list[datetime]] = {}
        for document_id, at in rows:
            found.setdefault(document_id, []).append(at)
        for at_list in found.values():
            at_list.sort()
        return found

    @staticmethod
    async def _answers(documents: list[GuideDocument]) -> dict[int, str]:
        if not documents:
            return {}
        rows = await CheckIn.filter(guide_document_id__in=[row.guide_document_id for row in documents]).values_list(
            "guide_document_id", "medication"
        )
        return {document_id: str(answer) for document_id, answer in rows}

    @staticmethod
    async def _courses(visit_ids: list[int]) -> dict[int, tuple[str, int | None]]:
        """세트명과 처방일수. 약이 여럿이면 **가장 긴 일수**를 쓴다 —
        「비잔 84일 + 진통제(빈칸)」에서 84 를 잃으면 안 된다."""
        if not visit_ids:
            return {}
        rows = await Prescription.filter(visit_id__in=visit_ids).values_list(
            "visit_id", "prescription_set", "items__duration_days"
        )
        found: dict[int, tuple[str, int | None]] = {}
        for visit_id, name, duration in rows:
            before = found.get(visit_id)
            longest = before[1] if before else None
            if duration and (longest is None or duration > longest):
                longest = duration
            found[visit_id] = (name, longest)
        return found

    @staticmethod
    async def _doctor(visits: list[Visit], hospital_id: int) -> Staff | None:
        """**가장 최근 진료의 담당**이다. 환자에 붙은 값이 아니다."""
        for visit in visits:
            if visit.doctor_id is not None:
                return await Staff.get_or_none(staff_id=visit.doctor_id, hospital_id=hospital_id)
        return None

    @staticmethod
    async def _diagnosis(visit_ids: list[int], hospital_id: int) -> str | None:
        if not visit_ids:
            return None
        rows = await OcrField.filter(
            ocr_result__ocr_job__visit_id__in=visit_ids,
            ocr_result__ocr_job__hospital_id=hospital_id,
            field_type="DIAGNOSIS",
            is_confirmed=True,
        ).values_list("corrected_value", "extracted_value")
        for corrected, extracted in rows:
            if corrected or extracted:
                return corrected or extracted
        return None

    # ── 한 블록 안 ───────────────────────────────────────

    @staticmethod
    def _guide_sent(sent: dict[str, GuideMessage]) -> datetime | None:
        row = sent.get(str(GuideMessageKind.GUIDE))
        if row is None or row.status is not GuideMessageStatus.SENT:
            return None
        return row.sent_at

    @staticmethod
    def _first(views: list[datetime]) -> datetime | None:
        return views[0] if views else None

    @staticmethod
    def _checks(
        sent: dict[str, GuideMessage],
        views: list[datetime],
        answer: str | None,
    ) -> list[HistoryCheck]:
        """확인 문자 줄들 — 원문 「일주일 뒤 05-27 미열람 · 보름 뒤 06-04 미열람」.

        **열람을 문자에 붙이는 규칙.** 열람 이벤트는 안내문에 달리지 문자에
        달리지 않는다. 그래도 시각이 남으므로, 이 문자가 나간 뒤 **다음 문자
        전까지** 열었으면 이 문자를 보고 연 것으로 읽는다. 완벽하지는 않지만
        「어느 문자가 환자를 다시 데려왔나」에 답할 수 있는 유일한 방법이고,
        틀려도 한 칸 옆으로 밀릴 뿐이다.
        """
        rows = [sent[str(kind)] for kind in CHECK_KINDS if str(kind) in sent]
        rows.sort(key=lambda row: row.scheduled_at)
        found = []
        for index, row in enumerate(rows):
            at = row.sent_at or row.scheduled_at
            after = rows[index + 1].sent_at or rows[index + 1].scheduled_at if index + 1 < len(rows) else None
            seen = [when for when in views if when >= at and (after is None or when < after)]
            found.append(
                HistoryCheck(
                    kind=row.kind,
                    at=at,
                    sent=row.status is GuideMessageStatus.SENT,
                    viewed_at=seen[0] if seen else None,
                    #: 응답은 D+7 것만이다 — 안내문당 한 건뿐이라 회차를 가를 수 없다.
                    answer=answer if row.kind is GuideMessageKind.CHECK_D7 else None,
                )
            )
        return found

    @staticmethod
    def _runs_out(visited_on: date, course: tuple[str, int | None] | None) -> date | None:
        if course is None or course[1] is None:
            return None
        return visited_on + timedelta(days=course[1])
