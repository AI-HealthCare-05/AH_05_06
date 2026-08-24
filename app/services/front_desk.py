from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.core.api_errors import ApiError
from app.core.pagination import encode_cursor
from app.core.time import DISPLAY_TIMEZONE
from app.dependencies.patient_access import ClinicalActor
from app.dtos.front_desk import FrontDeskVisitItem
from app.dtos.patients import calculate_age
from app.dtos.visits import DoctorResponse
from app.models.ocr import OcrField
from app.models.staffs import Staff
from app.repositories.visit_repository import VisitRepository
from app.services.patient_visit_scope import hospital_id_of, visit_cursor
from app.services.work_category import WorkCategory, count_by_category, derive, load_signals


@dataclass(frozen=True, slots=True)
class FrontDeskVisitPage:
    items: list[FrontDeskVisitItem]
    counts: dict[WorkCategory, int]
    selected: list[WorkCategory]
    next_cursor: str | None
    has_next: bool


class FrontDeskService:
    def __init__(self) -> None:
        self.repo = VisitRepository()

    async def list_visits(
        self,
        actor: ClinicalActor,
        *,
        target_date: date,
        categories: str | None,
        cursor: str | None,
        limit: int,
    ) -> FrontDeskVisitPage:
        hospital_id = hospital_id_of(actor)
        selected = self._categories(categories)
        before_at, before_id = visit_cursor(cursor)

        start_local = datetime.combine(target_date, time.min, tzinfo=DISPLAY_TIMEZONE)
        visits = await self.repo.front_desk_candidates(
            hospital_id,
            start_utc=start_local.astimezone(UTC),
            end_utc=(start_local + timedelta(days=1)).astimezone(UTC),
        )
        signals = await load_signals([visit.visit_id for visit in visits], hospital_id)
        derived = {visit_id: derive(value) for visit_id, value in signals.items()}
        eligible = [
            visit
            for visit in visits
            if visit.visit_id in derived
            and (
                visit.visited_at.astimezone(DISPLAY_TIMEZONE).date() == target_date
                or derived[visit.visit_id][0] is WorkCategory.NEEDS_ATTENTION
            )
        ]
        raw_counts = count_by_category({visit.visit_id: derived[visit.visit_id] for visit in eligible})
        counts = {category: raw_counts[category.value] for category in WorkCategory}
        filtered = [visit for visit in eligible if derived[visit.visit_id][0] in selected]
        if before_at is not None and before_id is not None:
            filtered = [visit for visit in filtered if (visit.visited_at, visit.visit_id) < (before_at, before_id)]
        has_next = len(filtered) > limit
        page_rows = filtered[:limit]

        doctor_ids = {visit.doctor_id for visit in page_rows if visit.doctor_id is not None}
        doctors = (
            {staff.staff_id: staff for staff in await Staff.filter(hospital_id=hospital_id, staff_id__in=doctor_ids)}
            if doctor_ids
            else {}
        )
        diagnoses = await self._diagnoses([visit.visit_id for visit in page_rows], hospital_id)
        items: list[FrontDeskVisitItem] = []
        for visit in page_rows:
            doctor = doctors.get(visit.doctor_id) if visit.doctor_id is not None else None
            work_category, detail_status = derived[visit.visit_id]
            items.append(
                FrontDeskVisitItem(
                    visit_id=visit.visit_id,
                    patient_id=visit.patient_id,
                    name=visit.patient.name,
                    hospital_patient_no=visit.patient.hospital_patient_no,
                    birth_date=visit.patient.birth_date,
                    age=calculate_age(visit.patient.birth_date, as_of=target_date),
                    diagnosis_name=diagnoses.get(visit.visit_id),
                    doctor=(
                        DoctorResponse(doctor_id=doctor.staff_id, name=doctor.name) if doctor is not None else None
                    ),
                    visited_at=visit.visited_at,
                    work_category=work_category,
                    detail_status=detail_status,
                )
            )
        next_cursor = None
        if has_next and page_rows:
            next_cursor = encode_cursor(
                {"visited_at": page_rows[-1].visited_at.isoformat(), "visit_id": page_rows[-1].visit_id}
            )
        return FrontDeskVisitPage(items, counts, selected, next_cursor, has_next)

    @staticmethod
    async def _diagnoses(visit_ids: list[int], hospital_id: int) -> dict[int, str]:
        if not visit_ids:
            return {}
        rows = await OcrField.filter(
            ocr_result__ocr_job__visit_id__in=visit_ids,
            ocr_result__ocr_job__hospital_id=hospital_id,
            field_type="DIAGNOSIS",
            is_confirmed=True,
        ).values_list(
            "ocr_result__ocr_job__visit_id",
            "corrected_value",
            "extracted_value",
        )
        return {visit_id: corrected or extracted for visit_id, corrected, extracted in rows if corrected or extracted}

    @staticmethod
    def _categories(raw: str | None) -> list[WorkCategory]:
        if not raw:
            return list(WorkCategory)
        try:
            selected = list(dict.fromkeys(WorkCategory(value.strip()) for value in raw.split(",") if value.strip()))
        except ValueError as error:
            raise ApiError(400, "INVALID_REQUEST", "업무 카테고리가 올바르지 않습니다.") from error
        if not selected:
            raise ApiError(400, "INVALID_REQUEST", "업무 카테고리를 하나 이상 선택해 주세요.")
        return selected
