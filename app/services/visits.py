import builtins
from datetime import UTC, datetime, timedelta

from tortoise.timezone import now

from app.core.api_errors import ApiError
from app.core.pagination import encode_cursor
from app.core.time import DISPLAY_TIMEZONE
from app.dependencies.patient_access import ClinicalActor
from app.dtos.visits import DoctorResponse, VisitCreateRequest, VisitResponse, VisitUpdateRequest
from app.models.ocr import OcrJob, OcrJobStatus
from app.models.staffs import Staff, StaffRole
from app.models.visits import GuideDocument, GuideStatus, Visit
from app.repositories.patient_repository import PatientRepository
from app.repositories.visit_repository import VisitRepository
from app.services.patient_visit_scope import hospital_id_of, visit_cursor

SIGNED_BIGINT_MAX = (1 << 63) - 1


class VisitService:
    def __init__(self) -> None:
        self.repo = VisitRepository()
        self.patient_repo = PatientRepository()

    async def create(self, actor: ClinicalActor, patient_id: int, data: VisitCreateRequest) -> Visit:
        hospital_id = hospital_id_of(actor)
        patient = await self.patient_repo.get_scoped(patient_id, hospital_id)
        if patient is None:
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")
        await self._validate_doctor(data.doctor_id, hospital_id)
        self._validate_department(data.department_id)
        await self._ensure_unique_day(patient_id, hospital_id, data.visited_at)

        values = data.model_dump(exclude={"department_id"})
        values.update(hospital_id=hospital_id, patient=patient, department=None)
        return await self.repo.create(values)

    async def get(self, actor: ClinicalActor, visit_id: int) -> Visit:
        visit = await self.repo.get_scoped(visit_id, hospital_id_of(actor))
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
        hospital_id = hospital_id_of(actor)
        if await self.patient_repo.get_scoped(patient_id, hospital_id) is None:
            raise ApiError(404, "PATIENT_NOT_FOUND", "환자를 찾을 수 없습니다.")
        before_at, before_id = visit_cursor(cursor)
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

        await self._validate_relation_update(visit, data, supplied)

        if "department_id" in supplied:
            self._validate_department(data.department_id)

        if "doctor_id" in supplied:
            await self._validate_doctor(data.doctor_id, hospital_id_of(actor))

        if "visited_at" in supplied:
            assert data.visited_at is not None
            await self._ensure_unique_day(
                visit.patient_id,
                hospital_id_of(actor),
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
            visit.department = None  # type: ignore[assignment]  # Tortoise CharField nullability typing gap
            update_fields.add("department")
        visit.updated_at = now()
        update_fields.add("updated_at")
        await self.repo.save(visit, sorted(update_fields))
        return visit

    async def responses(self, actor: ClinicalActor, visits: builtins.list[Visit]) -> builtins.list[VisitResponse]:
        """담당의 이름을 한 번에 읽어 상세·목록 응답을 같은 모양으로 만든다."""
        hospital_id = hospital_id_of(actor)
        doctor_ids = {visit.doctor_id for visit in visits if visit.doctor_id is not None}
        doctors = (
            {staff.staff_id: staff for staff in await Staff.filter(hospital_id=hospital_id, staff_id__in=doctor_ids)}
            if doctor_ids
            else {}
        )
        responses: builtins.list[VisitResponse] = []
        for visit in visits:
            response = VisitResponse.model_validate(visit)
            if visit.doctor_id is not None and (staff := doctors.get(visit.doctor_id)) is not None:
                response.doctor = DoctorResponse(doctor_id=staff.staff_id, name=staff.name)
            responses.append(response)
        return responses

    async def _ensure_unique_day(
        self,
        patient_id: int,
        hospital_id: int,
        visited_at: datetime,
        *,
        exclude_visit_id: int | None = None,
    ) -> None:
        localized = self._localized(visited_at)
        start_local = datetime.combine(localized.date(), datetime.min.time(), tzinfo=DISPLAY_TIMEZONE)
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

    #: 진료의 **식별 관계**가 굳는 시점. 안내문이 이 상태에 들어서면 본문이 이미
    #: 이 환자의 검사값·처방으로 쓰여 있고, 곧 나간다.
    #:
    #: `STAFF_REVIEW` 와 `APPROVAL_RETURNED` 는 뺀다 — 둘 다 스탭이 아직 **쓰고
    #: 있는** 상태라, 진료과가 잘못 잡힌 것을 그때 고칠 수 있어야 한다.
    #:
    #: **다만 이 예외는 안내문 상태만 놓고 볼 때의 이야기다.** 안내문은 늘 OCR
    #: 확정 뒤에 생기므로, 스탭이 실제로 마주치는 조합은 언제나 「OCR 이미 있음
    #: + 안내문 어떤 상태」다. 그 경우 아래 OCR 검사가 먼저 걸려 이 예외까지
    #: 가지 않는다 — `test_visit_locked.py::TestOcrDecidesFirst` 참고.
    LOCKING_GUIDE_STATUSES = (GuideStatus.APPROVAL_PENDING, GuideStatus.SCHEDULED_TO_SEND)

    async def _validate_relation_update(
        self,
        visit: Visit,
        data: VisitUpdateRequest,
        supplied: set[str],
    ) -> None:
        if "visited_at" in supplied and data.visited_at is None:
            raise ApiError(400, "INVALID_REQUEST", "visited_at에는 null을 입력할 수 없습니다.")
        if self._changed_relation_fields(visit, data, supplied):
            await self._refuse_if_locked(visit)

    @staticmethod
    def _changed_relation_fields(
        visit: Visit,
        data: VisitUpdateRequest,
        supplied: set[str],
    ) -> set[str]:
        """본문에 포함됐다는 이유가 아니라 실제 식별 관계 변경만 골라낸다."""
        changed: set[str] = set()
        if "doctor_id" in supplied and data.doctor_id != visit.doctor_id:
            changed.add("doctor_id")
        if "visited_at" in supplied and data.visited_at != visit.visited_at:
            changed.add("visited_at")
        if "department_id" in supplied:
            # v1에는 진료과 기준 테이블과 ID 저장 칸이 아직 없다. non-null ID는
            # 언제나 스냅샷 변경 시도이고, null은 스냅샷이 있을 때만 삭제다.
            if data.department_id is not None or visit.department is not None:
                changed.add("department_id")
        return changed

    async def _refuse_if_locked(self, visit: Visit) -> None:
        """OCR 이나 승인 안내가 붙은 뒤에는 식별 관계를 바꿀 수 없다 (계약 §6).

        왜 막느냐 — 안내문 본문은 **이 진료의 맥락으로** 쓰인다. 승인해서 발송을
        기다리는 안내가 달린 진료의 진료과를 바꾸면, 나가는 글과 기록이 가리키는
        곳이 갈라진다. `guide_event` 에는 「승인했다」만 남아 있어 나중에 무엇을
        승인한 것이었는지 되짚을 수 없다. 의무기록이라 조용히 어긋나면 복구할
        근거가 없다.

        판단은 **진료를 타고** 한다 — `GuideService.get()` 이 병원을 진료를 타고
        보는 것과 같은 이유다. 같은 값을 두 곳에 두면 어긋날 자리도 함께 생긴다.

        **두 검사의 순서가 결과를 정한다.** OCR 검사를 먼저 두었기 때문에,
        `LOCKING_GUIDE_STATUSES` 가 `STAFF_REVIEW`·`APPROVAL_RETURNED` 를 빼
        두어도 실제로는 거의 항상 OCR 쪽에서 먼저 막힌다 — 안내문이 그 상태에
        있다는 것 자체가 이미 OCR 이 끝났다는 뜻이기 때문이다. 이 예외가
        실제로 열리는 경우는 「OCR 없이 안내문만 있는」 것뿐인데, 지금 흐름상
        그런 진료는 생기지 않는다.
        """
        active_ocr = await OcrJob.filter(
            visit_id=visit.visit_id,
            status__in=(OcrJobStatus.PROCESSING, OcrJobStatus.COMPLETED),
        ).exists()
        if active_ocr:
            raise ApiError(409, "VISIT_LOCKED", "판독이 시작된 진료는 식별 관계를 바꿀 수 없습니다.")
        locked_guide = await GuideDocument.filter(
            visit_id=visit.visit_id, status__in=self.LOCKING_GUIDE_STATUSES
        ).exists()
        if locked_guide:
            raise ApiError(409, "VISIT_LOCKED", "승인 안내가 연결된 진료는 식별 관계를 바꿀 수 없습니다.")

    @staticmethod
    async def _validate_doctor(doctor_id: int | None, hospital_id: int) -> None:
        """같은 병원의 재직 중인 의사만 담당의가 될 수 있다.

        모든 거부 조건을 같은 오류로 답해 직원 ID의 존재 여부나 다른 병원의
        인력 정보를 응답으로 구분해 노출하지 않는다. `null`은 미지정·해제다.
        """
        if doctor_id is None:
            return
        # MySQL BIGINT 범위를 벗어난 값은 ORM 질의까지 보내면 OverflowError로 500이
        # 된다. 필드 범위 오류도 v1 계약의 400 INVALID_REQUEST로 정규화한다.
        if doctor_id < 1 or doctor_id > SIGNED_BIGINT_MAX:
            raise ApiError(400, "INVALID_REQUEST", "담당의를 확인해 주세요.")
        doctor = await Staff.get_or_none(staff_id=doctor_id, hospital_id=hospital_id)
        if doctor is None or not doctor.has_role(StaffRole.DOCTOR):
            raise ApiError(400, "INVALID_REQUEST", "담당의를 확인해 주세요.")

    @staticmethod
    def _validate_department(department_id: int | None) -> None:
        """진료과만 막는다.

        `department` 는 「검증된 진료과 명칭의 진료 당시 스냅샷」이라(계약 §4)
        진료과 표 없이는 저장할 이름 자체가 없다. 그래서 여기는 계속 막는다.

        `doctor_id` 는 사정이 다르다 — 이미 있는 nullable bigint 라 저장할 자리가
        있고, 막았던 이유는 소속을 **검증할** 표가 없어서였다. 저장까지 막으면
        `visit.doctor_id` 가 영원히 NULL 이라 목록의 「담당」이 전부 비고, 의사가
        자기 환자만 보는 D1-1 이 성립하지 않는다. 검증은 KEY-73 의 `Staff` 가
        develop 에 올라간 뒤 붙인다.

        `INVALID_DEPARTMENT` 는 계약 §7 에서 진료과 전용 코드다. 담당의만 보냈는데
        이 코드가 오면 화면은 없는 진료과를 고쳐 보내려 한다.
        """
        if department_id is not None:
            raise ApiError(
                400,
                "INVALID_DEPARTMENT",
                "진료과 검증 기준 데이터가 준비되지 않았습니다.",
            )

    @staticmethod
    def _localized(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ApiError(400, "INVALID_REQUEST", "visited_at에는 시간대가 필요합니다.")
        return value.astimezone(DISPLAY_TIMEZONE)
