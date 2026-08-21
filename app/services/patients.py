from collections.abc import Sequence

from tortoise.exceptions import IntegrityError
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.dependencies.patient_access import ClinicalActor
from app.dtos.patients import PatientCreateRequest, PatientUpdateRequest
from app.models.patients import Patient, PatientNumberCorrection
from app.models.visits import Visit
from app.repositories.patient_repository import PatientRepository


class PatientService:
    def __init__(self) -> None:
        self.repo = PatientRepository()

    async def create(self, actor: ClinicalActor, data: PatientCreateRequest) -> Patient:
        hospital_id = self._hospital_id(actor)
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
        patient = await self.repo.get_scoped(patient_id, self._hospital_id(actor))
        if patient is None:
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")
        return patient

    async def list(
        self,
        actor: ClinicalActor,
        *,
        keyword: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[tuple[Patient, Visit | None]], str | None, bool]:
        after_id = self._patient_cursor(cursor)
        hospital_id = self._hospital_id(actor)
        rows = await self.repo.list_scoped(
            hospital_id,
            keyword=keyword.strip() if keyword else None,
            after_id=after_id,
            limit=limit + 1,
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        items = [(patient, await self.repo.latest_visit(patient.patient_id, hospital_id)) for patient in rows]
        next_cursor = encode_cursor({"patient_id": rows[-1].patient_id}) if has_next and rows else None
        return items, next_cursor, has_next

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
                hospital_id=self._hospital_id(actor),
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
        hospital_id = self._hospital_id(actor)
        if "admin" not in actor.roles:
            raise ApiError(403, "FORBIDDEN", "환자번호를 정정할 권한이 없습니다.")
        if await self.repo.has_visits(patient.patient_id, hospital_id):
            raise ApiError(409, "PATIENT_NUMBER_LOCKED", "진료가 등록된 환자번호는 수정할 수 없습니다.")
        assert data.hospital_patient_no is not None
        duplicate = await self.repo.get_by_number(hospital_id, data.hospital_patient_no)
        if duplicate is not None and duplicate.patient_id != patient.patient_id:
            self._raise_duplicate()
        patient.hospital_patient_no = data.hospital_patient_no

    @staticmethod
    def _hospital_id(actor: ClinicalActor) -> int:
        assert actor.hospital_id is not None
        return actor.hospital_id

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
