from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from tortoise.timezone import now

from app.core.api_errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.dependencies.patient_access import ClinicalActor
from app.dtos.visits import VisitCreateRequest, VisitUpdateRequest
from app.models.visits import Visit
from app.repositories.patient_repository import PatientRepository
from app.repositories.visit_repository import VisitRepository

SEOUL = ZoneInfo("Asia/Seoul")


class VisitService:
    def __init__(self) -> None:
        self.repo = VisitRepository()
        self.patient_repo = PatientRepository()

    async def create(self, actor: ClinicalActor, patient_id: int, data: VisitCreateRequest) -> Visit:
        hospital_id = self._hospital_id(actor)
        patient = await self.patient_repo.get_scoped(patient_id, hospital_id)
        if patient is None:
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")
        self._validate_directory_fields(data.doctor_id, data.department_id)
        await self._ensure_unique_day(patient_id, hospital_id, data.visited_at)

        values = data.model_dump(exclude={"department_id"})
        values.update(hospital_id=hospital_id, patient=patient, department=None)
        return await self.repo.create(values)

    async def get(self, actor: ClinicalActor, visit_id: int) -> Visit:
        visit = await self.repo.get_scoped(visit_id, self._hospital_id(actor))
        if visit is None:
            raise ApiError(404, "VISIT_NOT_FOUND", "진료를 찾을 수 없습니다.")
        return visit

    async def list(
        self,
        actor: ClinicalActor,
        patient_id: int,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Visit], str | None, bool]:
        hospital_id = self._hospital_id(actor)
        if await self.patient_repo.get_scoped(patient_id, hospital_id) is None:
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")
        before_at, before_id = self._visit_cursor(cursor)
        rows = await self.repo.list_scoped(
            patient_id,
            hospital_id,
            before_visited_at=before_at,
            before_visit_id=before_id,
            limit=limit + 1,
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_next and rows:
            next_cursor = encode_cursor(
                {
                    "visited_at": rows[-1].visited_at.isoformat(),
                    "visit_id": rows[-1].visit_id,
                }
            )
        return rows, next_cursor, has_next

    async def update(self, actor: ClinicalActor, visit_id: int, data: VisitUpdateRequest) -> Visit:
        visit = await self.get(actor, visit_id)
        supplied = data.model_fields_set
        if not supplied:
            raise ApiError(400, "EMPTY_UPDATE_FIELDS", "수정할 필드가 없습니다.")

        if "doctor_id" in supplied or "department_id" in supplied:
            self._validate_directory_fields(data.doctor_id, data.department_id)

        if "visited_at" in supplied:
            if data.visited_at is None:
                raise ApiError(400, "INVALID_REQUEST", "visited_at에는 null을 입력할 수 없습니다.")
            await self._ensure_unique_day(
                visit.patient_id,
                self._hospital_id(actor),
                data.visited_at,
                exclude_visit_id=visit.visit_id,
            )

        update_fields = supplied - {"department_id"}
        for required_field in {"status", "planned_stop"} & update_fields:
            if getattr(data, required_field) is None:
                raise ApiError(400, "INVALID_REQUEST", f"{required_field}에는 null을 입력할 수 없습니다.")
        for field in update_fields:
            setattr(visit, field, getattr(data, field))
        if "department_id" in supplied:
            visit.department = None
            update_fields.add("department")
        visit.updated_at = now()
        update_fields.add("updated_at")
        await self.repo.save(visit, sorted(update_fields))
        return visit

    async def _ensure_unique_day(
        self,
        patient_id: int,
        hospital_id: int,
        visited_at: datetime,
        *,
        exclude_visit_id: int | None = None,
    ) -> None:
        localized = self._localized(visited_at)
        start_local = datetime.combine(localized.date(), datetime.min.time(), tzinfo=SEOUL)
        start_utc = start_local.astimezone(UTC)
        end_utc = (start_local + timedelta(days=1)).astimezone(UTC)
        if await self.repo.exists_on_day(
            patient_id,
            hospital_id,
            start_utc,
            end_utc,
            exclude_visit_id=exclude_visit_id,
        ):
            raise ApiError(409, "VISIT_ALREADY_REGISTERED", "같은 날짜의 진료가 이미 등록되어 있습니다.")

    @staticmethod
    def _validate_directory_fields(doctor_id: int | None, department_id: int | None) -> None:
        if doctor_id is not None or department_id is not None:
            raise ApiError(
                400,
                "INVALID_DEPARTMENT",
                "진료과·담당의 검증 기준 데이터가 준비되지 않았습니다.",
            )

    @staticmethod
    def _localized(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ApiError(400, "INVALID_REQUEST", "visited_at에는 시간대가 필요합니다.")
        return value.astimezone(SEOUL)

    @staticmethod
    def _hospital_id(actor: ClinicalActor) -> int:
        assert actor.hospital_id is not None
        return actor.hospital_id

    @staticmethod
    def _visit_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
        try:
            payload = decode_cursor(cursor)
            if payload is None:
                return None, None
            visit_id = payload.get("visit_id")
            visited_at = payload.get("visited_at")
            if not isinstance(visit_id, int) or not isinstance(visited_at, str):
                raise ValueError
            parsed = datetime.fromisoformat(visited_at)
            if parsed.tzinfo is None:
                raise ValueError
            return parsed, visit_id
        except ValueError as error:
            raise ApiError(400, "INVALID_REQUEST", "페이지 커서가 올바르지 않습니다.") from error
