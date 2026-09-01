import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from tortoise.exceptions import IntegrityError
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.time import DISPLAY_TIMEZONE
from app.dependencies.patient_access import ClinicalActor
from app.dtos.patients import PatientCategory, PatientCreateRequest, PatientUpdateRequest
from app.models.ocr import OcrField
from app.models.patients import Patient, PatientNumberCorrection
from app.models.staffs import Staff
from app.models.visits import Visit
from app.repositories.patient_repository import PatientRepository
from app.services.patient_flags import PatientFlag, flags_of, load_flag_inputs, stopped_dosing
from app.services.patient_visit_scope import hospital_id_of
from app.services.work_category import DetailStatus, WorkCategory, derive, load_signals

#: 최근 진료의 상태로 갈리는 분류 — 와이어프레임 S2-1 의 칩 둘.
#:
#: **환자에 붙은 값이 아니라 진료에서 나온 값이다.** 그래서 표를 걸러 세지
#: 못하고, 최근 진료들을 읽어 셈해야 한다. 예전에는 그럴 자리가 없어 400 으로
#: 막고 0 으로 세고 있었다.
EVENT_PATIENT_CATEGORIES = frozenset({PatientCategory.IN_TREATMENT, PatientCategory.NEEDS_ATTENTION})


@dataclass(frozen=True, slots=True)
class PatientRow:
    """표 한 줄에 실릴 것 — 환자 · 최근 진료 · 거기서 나온 것들."""

    patient: Patient
    latest_visit: Visit | None
    diagnosis_name: str | None
    doctor: Staff | None
    work_category: WorkCategory | None
    detail_status: DetailStatus | None
    flags: list[str]


class PatientService:
    def __init__(self) -> None:
        self.repo = PatientRepository()

    async def create(self, actor: ClinicalActor, data: PatientCreateRequest) -> Patient:
        hospital_id = hospital_id_of(actor)
        if await self.repo.get_by_number(hospital_id, data.hospital_patient_no):
            self._raise_duplicate()

        timestamp = now()
        values = data.model_dump()
        values.update(
            hospital_id=hospital_id,
            sms_consented_at=timestamp if data.sms_consent else None,
            sms_opted_out_at=None if data.sms_consent else timestamp,
            sms_consent_updated_by=actor.staff_id,
        )
        try:
            return await self.repo.create(values)
        except IntegrityError as error:
            raise ApiError(
                409,
                "DUPLICATE_HOSPITAL_PATIENT_NO",
                "같은 병원에 이미 등록된 환자번호입니다.",
            ) from error

    async def get(self, actor: ClinicalActor, patient_id: int) -> Patient:
        patient = await self.repo.get_scoped(patient_id, hospital_id_of(actor))
        if patient is None:
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")
        return patient

    async def list(
        self,
        actor: ClinicalActor,
        *,
        keyword: str | None,
        category: PatientCategory,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[PatientRow], dict[PatientCategory, int], str | None, bool]:
        """환자 관리 표 — 와이어프레임 S2-1.

        **분류가 두 갈래다.**

        환자에 붙은 값(수신 거부 · 6개월 이상 미내원)은 표를 걸러 셀 수 있다.
        진료에서 나오는 값(진행 중 · 챙겨주세요)은 그럴 수 없다 — 최근 진료를
        읽어 상태를 내야 알 수 있다. 뒤엣것을 위해 **의원의 최근 진료를 한 번
        훑는다.** 훑지 않고 화면에 보이는 쪽만 세면 「전체 128명 중 진행 중
        34」가 아니라 「이 쪽에 보이는 20명 중 진행 중 3」이 되어, 스탭이
        일이 없다고 믿게 된다.
        """
        after_id = self._patient_cursor(cursor)
        hospital_id = hospital_id_of(actor)
        keyword = keyword.strip() if keyword else None
        cutoff_date = self._months_before(now().astimezone(DISPLAY_TIMEZONE).date(), 6)
        inactive_before = datetime.combine(cutoff_date, time.min, tzinfo=DISPLAY_TIMEZONE).astimezone(UTC)
        latest_times = await self.repo.latest_visit_times(hospital_id)
        inactive_patient_ids = [
            patient_id for patient_id, visited_at in latest_times.items() if visited_at < inactive_before
        ]

        by_event = await self._event_categories(hospital_id, list(latest_times))
        wanted = by_event.get(category) if category in EVENT_PATIENT_CATEGORIES else None

        rows = await self.repo.list_scoped(
            hospital_id,
            keyword=keyword,
            after_id=after_id,
            limit=limit + 1,
            sms_opt_out_only=category is PatientCategory.SMS_OPT_OUT,
            patient_ids=(
                inactive_patient_ids
                if category is PatientCategory.INACTIVE_6_MONTHS
                else (sorted(wanted) if wanted is not None else None)
            ),
        )
        all_count, sms_opt_out_count, inactive_count = await self.repo.category_counts(
            hospital_id,
            keyword=keyword,
            inactive_patient_ids=inactive_patient_ids,
        )
        counts = {
            PatientCategory.ALL: all_count,
            PatientCategory.IN_TREATMENT: len(by_event[PatientCategory.IN_TREATMENT]),
            PatientCategory.NEEDS_ATTENTION: len(by_event[PatientCategory.NEEDS_ATTENTION]),
            PatientCategory.SMS_OPT_OUT: sms_opt_out_count,
            PatientCategory.INACTIVE_6_MONTHS: inactive_count,
        }
        has_next = len(rows) > limit
        selected_rows = rows[:limit]
        items = await self._rows(selected_rows, hospital_id)
        next_cursor = (
            encode_cursor({"patient_id": selected_rows[-1].patient_id}) if has_next and selected_rows else None
        )
        return items, counts, next_cursor, has_next

    async def _event_categories(
        self,
        hospital_id: int,
        patient_ids: list[int],
    ) -> dict[PatientCategory, set[int]]:
        """진행 중 · 챙겨주세요에 드는 환자 번호.

        **접수대 목록과 같은 규칙으로 낸다**(`work_category.derive`). 여기서
        따로 셈하면 같은 환자가 두 화면에서 다르게 뜬다.
        """
        empty = {PatientCategory.IN_TREATMENT: set(), PatientCategory.NEEDS_ATTENTION: set()}
        if not patient_ids:
            return empty

        latest = await self.repo.latest_visits(patient_ids, hospital_id)
        if not latest:
            return empty

        signals = await load_signals([visit.visit_id for visit in latest.values()], hospital_id)
        flag_inputs = await load_flag_inputs(latest, hospital_id)
        stopped = await stopped_dosing(latest)
        today = now().astimezone(DISPLAY_TIMEZONE).date()

        in_treatment: set[int] = set()
        attention: set[int] = set()
        for patient_id, visit in latest.items():
            found = signals.get(visit.visit_id)
            category = derive(found)[0] if found else None
            if category is not None and category is not WorkCategory.COMPLETED:
                in_treatment.add(patient_id)
            marks = flags_of(flag_inputs[patient_id], today) if patient_id in flag_inputs else []
            if patient_id in stopped:
                marks = marks + [PatientFlag.STOPPED_DOSING]
            # **이탈도 챙길 일이다.** 원문에서 「완료 · 열람」인 줄에 ⚠ 배지가
            # 붙어 있다 — 진료는 끝났는데 환자가 이탈하는 자리라, 보완만
            # 세면 그 줄은 어느 칩에도 안 걸린다.
            if category is WorkCategory.NEEDS_ATTENTION or marks:
                attention.add(patient_id)
        return {
            PatientCategory.IN_TREATMENT: in_treatment,
            PatientCategory.NEEDS_ATTENTION: attention,
        }

    async def _rows(self, patients: list[Patient], hospital_id: int) -> list[PatientRow]:
        if not patients:
            return []
        patient_ids = [patient.patient_id for patient in patients]
        latest = await self.repo.latest_visits(patient_ids, hospital_id)
        visit_ids = [visit.visit_id for visit in latest.values()]

        signals = await load_signals(visit_ids, hospital_id) if visit_ids else {}
        flag_inputs = await load_flag_inputs(latest, hospital_id)
        stopped = await stopped_dosing(latest)
        diagnoses = await self._diagnoses(visit_ids, hospital_id)
        doctors = await self._doctors(latest, hospital_id)
        today = now().astimezone(DISPLAY_TIMEZONE).date()

        found = []
        for patient in patients:
            visit = latest.get(patient.patient_id)
            derived = derive(signals[visit.visit_id]) if visit and visit.visit_id in signals else None
            marks = flags_of(flag_inputs[patient.patient_id], today) if patient.patient_id in flag_inputs else []
            if patient.patient_id in stopped:
                marks = marks + [PatientFlag.STOPPED_DOSING]
            found.append(
                PatientRow(
                    patient=patient,
                    latest_visit=visit,
                    diagnosis_name=diagnoses.get(visit.visit_id) if visit else None,
                    doctor=doctors.get(visit.doctor_id) if visit and visit.doctor_id else None,
                    work_category=derived[0] if derived else None,
                    detail_status=derived[1] if derived else None,
                    flags=marks,
                )
            )
        return found

    @staticmethod
    async def _diagnoses(visit_ids: list[int], hospital_id: int) -> dict[int, str]:
        """확정된 진단만 온다 — `front_desk` 와 같은 규칙이다.

        판독 중인 값을 표에 올리면 의사가 아직 안 본 글자가 「이 환자의
        진단」으로 읽힌다.
        """
        if not visit_ids:
            return {}
        rows = await OcrField.filter(
            ocr_result__ocr_job__visit_id__in=visit_ids,
            ocr_result__ocr_job__hospital_id=hospital_id,
            field_type="DIAGNOSIS",
            is_confirmed=True,
        ).values_list("ocr_result__ocr_job__visit_id", "corrected_value", "extracted_value")
        return {visit_id: corrected or extracted for visit_id, corrected, extracted in rows if corrected or extracted}

    @staticmethod
    async def _doctors(latest: dict[int, Visit], hospital_id: int) -> dict[int, Staff]:
        doctor_ids = {visit.doctor_id for visit in latest.values() if visit.doctor_id is not None}
        if not doctor_ids:
            return {}
        return {staff.staff_id: staff for staff in await Staff.filter(hospital_id=hospital_id, staff_id__in=doctor_ids)}

    async def update(self, actor: ClinicalActor, patient_id: int, data: PatientUpdateRequest) -> Patient:
        patient = await self.get(actor, patient_id)
        supplied = data.model_fields_set
        mutable_fields = {"name", "birth_date", "gender", "phone", "sms_consent"}
        update_fields = supplied & mutable_fields

        # 바뀌기 **전** 번호를 여기서 붙잡는다. `_correct_patient_number()` 가
        # `patient.hospital_patient_no` 를 덮어쓰기 때문에 그 뒤에는 못 읽는다.
        correction: tuple[str, str] | None = None
        if "hospital_patient_no" in supplied:
            before_no = patient.hospital_patient_no
            await self._correct_patient_number(actor, patient, data)
            correction = (before_no, patient.hospital_patient_no)
            update_fields.add("hospital_patient_no")

        if not update_fields:
            raise ApiError(400, "EMPTY_UPDATE_FIELDS", "수정할 필드가 없습니다.")

        for field in update_fields - {"hospital_patient_no"}:
            value = getattr(data, field)
            if value is None:
                raise ApiError(400, "INVALID_REQUEST", f"{field}에는 null을 입력할 수 없습니다.")
            setattr(patient, field, value)

        if "sms_consent" in update_fields:
            timestamp = now()
            patient.sms_consented_at = timestamp if patient.sms_consent else None
            patient.sms_opted_out_at = None if patient.sms_consent else timestamp
            patient.sms_consent_updated_by = actor.staff_id
            update_fields.update({"sms_consented_at", "sms_opted_out_at", "sms_consent_updated_by"})

        patient.updated_at = now()
        update_fields.add("updated_at")
        try:
            if correction is None:
                await self.repo.save(patient, sorted(update_fields))
            else:
                await self._save_correction(actor, patient, sorted(update_fields), correction, data)
        except IntegrityError as error:
            # 트랜잭션 안에서 터졌다면 이미 되돌아간 뒤다 — 번호도 감사 기록도
            # 남지 않는다. 여기서는 계약이 정한 봉투로 바꿔 주기만 한다.
            raise ApiError(
                409,
                "DUPLICATE_HOSPITAL_PATIENT_NO",
                "같은 병원에 이미 등록된 환자번호입니다.",
            ) from error
        return patient

    async def _save_correction(
        self,
        actor: ClinicalActor,
        patient: Patient,
        # `list[str]` 이 아니라 `Sequence[str]` 인 이유 — 이 클래스에 `list()`
        # 메서드가 있어서, 그 뒤에 정의되는 메서드의 본문 주석에서 `list` 는
        # 내장 타입이 아니라 **그 메서드**를 가리킨다. `list[str]` 은 그대로
        # `TypeError: 'function' object is not subscriptable` 이 된다.
        fields: Sequence[str],
        correction: tuple[str, str],
        data: PatientUpdateRequest,
    ) -> None:
        """번호를 바꾸는 것과 **왜 바꿨는지 남기는 것**은 한 트랜잭션이다.

        갈라 두면 번호만 바뀌고 사유가 빈 행이 생긴다. 의무기록 정정이라
        그 간극은 나중에 메울 수 없다 — 「누가 왜 이 번호를 고쳤나」에
        답할 근거가 사라진 뒤다. 감사 기록이 실패하면 번호도 되돌아간다.
        """
        before_no, after_no = correction
        reason = (data.correction_reason or "").strip()
        if not reason:
            # `PatientUpdateRequest` 가 번호와 사유를 짝으로 강제하므로 API 를
            # 통해서는 여기 닿지 않는다. 그래도 `assert` 로 두지 않는 이유는
            # **`-O` 에서 사라지기 때문**이다. 사유 없는 정정이 조용히 저장되면
            # 감사 기록이 있는데 거짓말을 하는 상태가 된다 — 없느니만 못하다.
            raise ApiError(422, "CORRECTION_REASON_REQUIRED", "환자번호를 고친 이유를 적어 주세요.")

        async with in_transaction() as connection:
            await self.repo.save(patient, fields, using_db=connection)
            await PatientNumberCorrection.create(
                hospital_id=hospital_id_of(actor),
                patient_id=patient.patient_id,
                before_no=before_no,
                after_no=after_no,
                reason=reason,
                corrected_by=actor.staff_id,
                using_db=connection,
            )

    async def _correct_patient_number(
        self,
        actor: ClinicalActor,
        patient: Patient,
        data: PatientUpdateRequest,
    ) -> None:
        hospital_id = hospital_id_of(actor)
        if "admin" not in actor.roles:
            raise ApiError(403, "FORBIDDEN", "환자번호를 정정할 권한이 없습니다.")
        if await self.repo.has_visits(patient.patient_id, hospital_id):
            raise ApiError(409, "PATIENT_NUMBER_LOCKED", "진료가 등록된 환자번호는 수정할 수 없습니다.")
        if data.hospital_patient_no is None:
            raise ApiError(422, "CORRECTION_REASON_REQUIRED", "환자번호와 정정 사유를 함께 입력해 주세요.")
        duplicate = await self.repo.get_by_number(hospital_id, data.hospital_patient_no)
        if duplicate is not None and duplicate.patient_id != patient.patient_id:
            self._raise_duplicate()
        patient.hospital_patient_no = data.hospital_patient_no

    @staticmethod
    def _months_before(value: date, months: int) -> date:
        index = value.year * 12 + value.month - 1 - months
        year, month_index = divmod(index, 12)
        month = month_index + 1
        return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))

    @staticmethod
    def _patient_cursor(cursor: str | None) -> int | None:
        try:
            payload = decode_cursor(cursor)
            if payload is None:
                return None
            patient_id = payload.get("patient_id")
            if not isinstance(patient_id, int):
                raise ValueError
            return patient_id
        except ValueError as error:
            raise ApiError(400, "INVALID_REQUEST", "페이지 커서가 올바르지 않습니다.") from error

    @staticmethod
    def _raise_duplicate() -> None:
        raise ApiError(
            409,
            "DUPLICATE_HOSPITAL_PATIENT_NO",
            "같은 병원에 이미 등록된 환자번호입니다.",
        )
