from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from fastapi import status
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.models.ocr import (
    OcrDocumentText,
    OcrDocumentType,
    OcrField,
    OcrFieldCandidate,
    OcrJob,
    OcrJobDocument,
    OcrJobStatus,
    OcrResult,
    course_days,
    read_but_unconfirmed,
)
from app.models.prescriptions import AS_NEEDED, Prescription, PrescriptionItem
from app.models.visits import Visit
from app.ocr.errors import OcrApiError
from app.ocr.schemas import (
    FinalizeOcrResponse,
    OcrCandidateResponse,
    OcrDocumentResponse,
    OcrFieldResponse,
    OcrJobByDocumentResponse,
    OcrJobResponse,
    OcrResultResponse,
    PrescriptionItemResponse,
    PreviousOcrFieldResponse,
    UpdateOcrFieldRequest,
)
from app.ocr.security import OcrActor
from app.ocr.utils import assert_ocr_jobs_ready, merge_fields_by_type


def _resolved_value(row: dict) -> str | None:
    return row["corrected_value"] if row["corrected_value"] is not None else row["extracted_value"]


#: 처방일수 칸의 이름. 접미사(`_2`, `_3` …)가 붙어 약마다 하나씩 온다.
#: 「3」이 3일인지 3통인지가 이 칸의 `unit` 에 붙는다 (KEY-271 · KEY-285).
_DURATION_FIELD = "DURATION_DAYS"


def _takes_duration_unit(field_type: str) -> bool:
    """단위를 붙일 수 있는 칸인가 — KEY-285.

    처방일수뿐이다. 접미사가 붙은 둘째 약(`DURATION_DAYS_2`)도 같은 칸이라
    함께 받는다 — 한 진료에 약이 둘이면 각자의 총투가 따로 온다.

    검사값(`HEMOGLOBIN` 등)의 단위는 **항목의 성질**이라 화면의 `FIELD_UNITS`
    가 갖는다. 그것을 요청으로 덮게 두면 같은 항목이 진료마다 다른 단위로
    보인다.
    """
    return field_type == _DURATION_FIELD or field_type.startswith(f"{_DURATION_FIELD}_")


def _refuse_unit_on_other_fields(unit: object, field_type: str) -> None:
    """**단위는 처방일수 줄에만 붙는다** — KEY-285.

    화면의 `fieldUnit` 이 **서버가 준 단위를 무조건 우선**하므로, 헤모글로빈
    줄에 「통」이 박히면 그 글자가 그대로 사람 눈에 붙는다. DTO 가 값의
    **모양**(`DurationUnit`)을 막고, 이 문이 붙일 **자리**를 막는다.

    고치기와 직접입력 두 길이 같은 문을 지난다 — 한쪽만 막으면 다른 쪽으로
    같은 값이 들어온다.
    """
    if unit is not None and not _takes_duration_unit(field_type):
        raise OcrApiError(
            status.HTTP_400_BAD_REQUEST,
            "UNIT_NOT_ALLOWED",
            "처방일수 항목에만 단위를 지정할 수 있습니다.",
        )


def _drop_confirmation(field: OcrField) -> None:
    """**값이 바뀌면 확정 도장을 뗀다** — KEY-273 뒤처리.

    확정은 「이 값을 사람이 봤다」는 도장이다. KEY-273 이 확정 뒤에도 고칠 수
    있게 열면서 도장을 그대로 두었더니, 도장이 **옛 값**을 가리킨 채 남았다.
    기록은 「스탭 A 가 T1 에 확인」인데 화면의 값은 스탭 B 가 T2 에 친 것이고,
    **그 값은 아무도 확인한 적이 없다.** 생성의 미확정 게이트는 통과한다.

    도장을 새 사람 이름으로 다시 찍는 것은 답이 아니다 — **값을 친 것과 값을
    확인한 것은 다른 행위다.** 뗀 뒤에는 화면에 「확인 전」으로 다시 서고,
    스탭이 보고 다시 확정한다 (이희진 님 `#221` ②).

    누가 언제 고쳤는지는 `modified_by`·`modified_at` 이 따로 든다 — 확인 기록만
    떨어지고 수정 기록은 남는다.
    """
    field.is_confirmed = False
    field.confirmed_by = None
    field.confirmed_at = None


class OcrRepository(Protocol):
    async def get_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob: ...

    async def get_latest_job_by_visit(self, visit_id: int, actor: OcrActor) -> OcrJob | None: ...

    async def get_latest_jobs_by_document(
        self, visit_id: int, actor: OcrActor
    ) -> list[tuple[OcrJobDocument, OcrJob]]: ...

    async def get_result(self, ocr_job_id: str, actor: OcrActor) -> OcrResult: ...

    async def get_fields(
        self, ocr_job_id: str, actor: OcrActor, field_type: str | None
    ) -> tuple[Sequence[OcrField], Sequence[OcrDocumentText]]: ...

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> tuple[OcrField, Sequence[OcrDocumentText]]: ...

    async def write_field(
        self,
        visit_id: int,
        field_type: str,
        value: str | None,
        actor: OcrActor,
        unit: str | None = None,
    ) -> tuple[OcrField | None, Sequence[OcrDocumentText]]: ...

    async def exclude_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob: ...

    async def get_previous_fields(self, visit_id: int, actor: OcrActor) -> list[PreviousOcrFieldResponse]: ...
    async def finalize_ocr(self, visit_id: int, actor: OcrActor) -> Prescription: ...


def _medication_suffixes(fields_by_type: dict[str, "OcrField"]) -> list[str]:
    """**있는 만큼 다 본다** — 다섯으로 끊지 않는다.

    예전에는 `("", "_2", "_3", "_4", "_5")` 를 손으로 적어 두었다. 그런데 판독
    확인 화면은 수동으로 더한 약을 **기존 최대 번호 다음**으로 담는다
    (`ocr-review.js` 의 `maxIdx + i + 1`) — 상한이 없다. 판독이 `_5` 까지 냈으면
    수동 약은 `_6` 이 되어 **여기서 조용히 빠졌다.**

    여태 티가 안 난 것은 이 함수의 결과가 어디에도 안 실렸기 때문이다. 화면이
    `ocr-finalize` 를 부르기 시작하면(KEY-271) 화면은 「저장했습니다」라 말하고
    안내문 복약 목록에서 그 약만 사라진다.

    차례는 번호 순이다 — 접미사 없는 것이 첫 약이고, 그 뒤로 `_2`, `_3` … 이다.
    화면이 그 차례로 보여 주므로 안내문도 같아야 한다.
    """
    found: list[tuple[int, str]] = []
    for name in fields_by_type:
        if name == "MEDICATION_NAME":
            found.append((1, ""))
            continue
        rest = name.removeprefix("MEDICATION_NAME_") if name.startswith("MEDICATION_NAME_") else None
        if rest is not None and rest.isdigit():
            found.append((int(rest), f"_{rest}"))
    return [suffix for _, suffix in sorted(found)]


def _collect_item_rows(
    fields_by_type: dict[str, "OcrField"],
) -> list[tuple[str, str, int | None]]:
    rows: list[tuple[str, str, int | None]] = []
    for suffix in _medication_suffixes(fields_by_type):
        med_field = fields_by_type.get(f"MEDICATION_NAME{suffix}")
        if med_field is None or not med_field.value:
            continue
        freq_field = fields_by_type.get(f"FREQUENCY{suffix}")
        frequency = freq_field.value if freq_field is not None and freq_field.value else ""
        dur_field = fields_by_type.get(f"{_DURATION_FIELD}{suffix}")
        duration_days: int | None = None
        if frequency != AS_NEEDED and dur_field is not None:
            # 판독이 읽은 숫자가 총투(통)일 수 있다 — `unit` 이 그것을 말한다.
            duration_days = course_days(dur_field.value, dur_field.unit)
        rows.append((med_field.value, frequency, duration_days))
    return rows


async def _result_of(job: OcrJob) -> "OcrResult | None":
    """그 판독 작업의 결과를 필드까지 붙여 가져온다."""
    return await OcrResult.filter(ocr_job_id=job.ocr_job_id).prefetch_related("fields").first()


async def _gather_results_from_jobs(
    jobs: list[OcrJob],
) -> tuple[list[OcrResult], dict[int, OcrDocumentType]]:
    """job 목록에서 OcrResult를 필드와 함께 수집하고 result_id→문서유형 매핑을 함께 반환한다."""
    results: list[OcrResult] = []
    doc_type_of: dict[int, OcrDocumentType] = {}
    for job in jobs:
        await job.fetch_related("source_documents")
        r = await _result_of(job)
        if r is not None:
            results.append(r)
            if job.source_documents:
                doc_type_of[r.ocr_result_id] = job.source_documents[0].document_type
    return results, doc_type_of


async def _find_result_for_field(visit_id: int, hospital_id: int, field_type: str) -> OcrResult:
    """비제외 COMPLETED job 전체에서 field_type을 가진 result, 없으면 최신 result를 반환한다."""
    completed_jobs = (
        await OcrJob.filter(
            visit_id=visit_id,
            hospital_id=hospital_id,
            excluded_from_guide=False,
            status=OcrJobStatus.COMPLETED,
        )
        .order_by("-created_at")
        .all()
    )
    if not completed_jobs:
        raise _not_found()

    fallback: OcrResult | None = None
    for job in completed_jobs:
        r = await OcrResult.filter(ocr_job_id=job.ocr_job_id).first()
        if r is None:
            continue
        if await OcrField.filter(ocr_result_id=r.ocr_result_id, field_type=field_type).exists():
            return r
        if fallback is None:
            fallback = r

    if fallback is None:
        raise _not_found()
    return fallback


def _not_confirmed() -> OcrApiError:
    """쓸 판독이 아직 없다 — `GuideService.generate()` 와 같은 말을 쓴다."""
    return OcrApiError(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "OCR_NOT_CONFIRMED",
        "확정된 OCR 항목이 없습니다. 먼저 판독을 확정해 주세요.",
    )


def _not_found() -> OcrApiError:
    return OcrApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "OCR 리소스를 찾을 수 없습니다.")


class TortoiseOcrRepository:
    async def get_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob:
        job = await OcrJob.filter(ocr_job_id=ocr_job_id, hospital_id=actor.hospital_id).first()
        if job is None:
            raise _not_found()
        return job

    async def get_latest_job_by_visit(self, visit_id: int, actor: OcrActor) -> OcrJob | None:
        # 두 단계 쿼리 — 단일 쿼리 전환 여부 검토 결과 (KEY-125)
        #
        # 규칙: PROCESSING 우선, 없으면 created_at 내림차순 최신.
        #
        # 단일 쿼리 후보:
        #   SELECT * FROM ocr_job
        #   WHERE visit_id=? AND hospital_id=?
        #   ORDER BY (status='PROCESSING') DESC, created_at DESC
        #   LIMIT 1;
        #
        # 전환하지 않은 이유 두 가지:
        #   1. 두 쿼리는 각자 한 규칙만 담아 독립적으로 테스트할 수 있다.
        #      test_ocr_repository.py가 PROCESSING-우선과 최신순을 서로 다른 행으로
        #      검증하는데, 단일 쿼리로 합치면 그 독립성이 사라진다.
        #   2. 성능 차이가 없다. PROCESSING job이 없는 일반 경우에 쿼리 1은
        #      인덱스 레인지 스캔으로 즉시 빈 결과를 반환하고, 쿼리 2만 행을 읽는다.
        #      PROCESSING job이 있으면 쿼리 1만 행을 읽고 쿼리 2는 실행되지 않는다.
        #
        # 생성 SQL (Tortoise → MySQL):
        #   쿼리 1: SELECT … WHERE visit_id=? AND hospital_id=? AND status='PROCESSING'
        #            ORDER BY created_at DESC LIMIT 1;
        #   쿼리 2: SELECT … WHERE visit_id=? AND hospital_id=?
        #            ORDER BY created_at DESC LIMIT 1;
        job = (
            await OcrJob.filter(
                visit_id=visit_id,
                hospital_id=actor.hospital_id,
                status=OcrJobStatus.PROCESSING,
            )
            .order_by("-created_at")
            .first()
        )
        if job is not None:
            return job
        return (
            await OcrJob.filter(
                visit_id=visit_id,
                hospital_id=actor.hospital_id,
            )
            .order_by("-created_at")
            .first()
        )

    async def get_latest_jobs_by_document(self, visit_id: int, actor: OcrActor) -> list[tuple[OcrJobDocument, OcrJob]]:
        # Jobs ordered newest-first; first occurrence per document_id is the latest job.
        jobs = await (
            OcrJob.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
            .order_by("-created_at")
            .prefetch_related("source_documents")
        )
        seen: dict[int, tuple[OcrJobDocument, OcrJob]] = {}
        for job in jobs:
            for jd in job.source_documents:
                if jd.document_id not in seen:
                    seen[jd.document_id] = (jd, job)
        return list(seen.values())

    async def get_result(self, ocr_job_id: str, actor: OcrActor) -> OcrResult:
        job = await self.get_job(ocr_job_id, actor)
        if job.status == OcrJobStatus.FAILED:
            raise OcrApiError(status.HTTP_409_CONFLICT, "OCR_FAILED", "OCR 처리가 실패했습니다.")
        if job.status != OcrJobStatus.COMPLETED:
            raise OcrApiError(status.HTTP_409_CONFLICT, "OCR_RESULT_NOT_READY", "OCR 결과가 아직 준비되지 않았습니다.")
        result = (
            await OcrResult.filter(ocr_job_id=ocr_job_id)
            .prefetch_related("documents", "fields", "fields__candidates")
            .first()
        )
        if result is None:
            raise _not_found()
        return result

    async def get_fields(
        self, ocr_job_id: str, actor: OcrActor, field_type: str | None
    ) -> tuple[Sequence[OcrField], Sequence[OcrDocumentText]]:
        result = await self.get_result(ocr_job_id, actor)
        fields = [field for field in result.fields if field_type is None or field.field_type == field_type]
        return sorted(fields, key=lambda field: field.ocr_field_id), list(result.documents)

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> tuple[OcrField, Sequence[OcrDocumentText]]:
        async with in_transaction() as connection:
            field = (
                await OcrField.filter(
                    ocr_field_id=ocr_field_id,
                    ocr_result__ocr_job__hospital_id=actor.hospital_id,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if field is None:
                raise _not_found()
            # **확정돼도 고칠 수 있다** (KEY-273, 2026-09-04 권일준 결정).
            #
            # 예전에는 여기서 409 를 냈다. 그런데 **판독이 틀리는 것이 정상**이고,
            # 확정 뒤에 알아차리면 그 진료는 손쓸 방법이 없었다 — 진단과 처방이
            # 어긋난 채 확정돼 안내문이 승인까지 갔고, DB 를 직접 고쳐야 풀렸다.
            #
            # 이미 만들어진 안내문은 영향받지 않는다. `GuideSection` 이 본문을
            # 제 사본으로 들고 있어서, 여기를 고쳐도 승인된 글은 그대로다.
            if field.version != request.base_version:
                raise OcrApiError(status.HTTP_409_CONFLICT, "VERSION_CONFLICT", "필드 버전이 변경되었습니다.")

            corrected_value = request.corrected_value.strip() if request.corrected_value is not None else None
            selected_candidate: OcrFieldCandidate | None = None
            if request.candidate_id is not None:
                selected_candidate = (
                    await OcrFieldCandidate.filter(
                        ocr_field_candidate_id=request.candidate_id,
                        ocr_field_id=field.ocr_field_id,
                    )
                    .using_db(connection)
                    .first()
                )
                if selected_candidate is None:
                    raise OcrApiError(
                        status.HTTP_400_BAD_REQUEST,
                        "INVALID_CANDIDATE",
                        "해당 필드의 후보값이 아닙니다.",
                    )
                corrected_value = selected_candidate.candidate_value
                await (
                    OcrFieldCandidate.filter(ocr_field_id=field.ocr_field_id)
                    .using_db(connection)
                    .update(is_selected=False)
                )
                selected_candidate.is_selected = True
                await selected_candidate.save(update_fields=("is_selected",), using_db=connection)

            _refuse_unit_on_other_fields(request.unit, field.field_type)

            changed_at = now()
            unit_changed = request.unit is not None and field.unit != request.unit.value
            #: **단위를 고치는 것은 값을 고치는 것이다.** 숫자가 그대로여도
            #: 소진 예정일과 문자 발송일이 통째로 바뀐다(3 → 84). 그래서 확정
            #: 도장을 떼는 것도, 판올림도 값 수정과 같이 다룬다 — 안 그러면
            #: 「확정됐다」가 확정한 사람이 못 본 일수를 가리키게 된다.
            value_changed = request.corrected_value is not None or selected_candidate is not None or unit_changed
            if request.corrected_value is not None or selected_candidate is not None:
                field.corrected_value = corrected_value
            if request.unit is not None:
                field.unit = request.unit.value
            if value_changed:
                field.modified_by = actor.staff_id
                field.modified_at = changed_at
            field.version += 1
            if request.confirm:
                field.is_confirmed = True
                field.confirmed_by = actor.staff_id
                field.confirmed_at = changed_at
            elif value_changed and field.is_confirmed:
                _drop_confirmation(field)
            await field.save(using_db=connection)
        await field.fetch_related("candidates")

        doc_text_ids = {field.document_text_id} if field.document_text_id is not None else set()
        doc_text_ids.update(c.document_text_id for c in field.candidates if c.document_text_id is not None)
        doc_texts = (
            await OcrDocumentText.filter(ocr_document_text_id__in=list(doc_text_ids)).all() if doc_text_ids else []
        )
        return field, doc_texts

    async def write_field(
        self,
        visit_id: int,
        field_type: str,
        value: str | None,
        actor: OcrActor,
        unit: str | None = None,
    ) -> tuple[OcrField | None, Sequence[OcrDocumentText]]:
        """판독이 못 읽은 값을 사람이 적어 넣는다 — 와이어프레임 S1-7 「직접 입력」.

        **고치기(PATCH)와 다른 길이다.** 저쪽은 있는 줄의 값을 바꾸고, 이쪽은
        **줄 자체가 없는** 것을 만든다. 판독이 못 찾은 항목은 레코드로 남지
        않아서, 화면이 값을 적어도 보낼 곳이 없었다.

        `confidence` 는 비운다. 사람이 적은 값에 기계의 확신을 붙이면, 화면이
        「낮은 확신」으로 다시 물어보거나 반대로 확신한 값처럼 보인다.
        """
        _refuse_unit_on_other_fields(unit, field_type)

        result = await _find_result_for_field(visit_id, actor.hospital_id, field_type)
        text = value.strip() if value is not None else ""

        async with in_transaction() as connection:
            field = (
                await OcrField.filter(ocr_result_id=result.ocr_result_id, field_type=field_type)
                .using_db(connection)
                .select_for_update()
                .first()
            )

            # 확정된 줄도 다시 적을 수 있다 — 위 `edit_field` 와 같은 까닭이다 (KEY-273).

            # 비우면 지운다 — 「빈 값으로 적었다」를 남기면 안 적은 것과 구별이 안 된다.
            if not text:
                if field is not None:
                    await field.delete(using_db=connection)
                return None, []

            changed_at = now()
            if field is None:
                field = await OcrField.create(
                    ocr_result_id=result.ocr_result_id,
                    field_type=field_type,
                    corrected_value=text,
                    unit=unit,
                    modified_by=actor.staff_id,
                    modified_at=changed_at,
                    using_db=connection,
                )
            else:
                changed = field.corrected_value != text or (unit is not None and field.unit != unit)
                field.corrected_value = text
                if unit is not None:
                    field.unit = unit
                field.modified_by = actor.staff_id
                field.modified_at = changed_at
                field.version += 1
                if changed and field.is_confirmed:
                    _drop_confirmation(field)
                await field.save(using_db=connection)

        await field.fetch_related("candidates")
        return field, []

    async def exclude_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJob:
        job = await self.get_job(ocr_job_id, actor)
        if not job.excluded_from_guide:
            job.excluded_from_guide = True
            await job.save(update_fields=("excluded_from_guide",))
        return job

    async def get_previous_fields(self, visit_id: int, actor: OcrActor) -> list[PreviousOcrFieldResponse]:
        """같은 환자의 이전 visit에서 확정된 OCR 필드를 field_type별로 최신 하나씩 반환.

        - 같은 병원(hospital_id) 범위만 조회한다 — 타 병원 데이터 차단.
        - excluded_from_guide=True job의 필드는 포함하지 않는다.
        - is_confirmed=True 필드만 포함한다.
        - field_type이 중복될 경우 가장 최근 방문의 값을 택한다.
        """
        current = await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id).first()
        if current is None:
            raise _not_found()

        prev_visits = (
            await Visit.filter(
                hospital_id=actor.hospital_id,
                patient_id=current.patient_id,
                visited_at__lt=current.visited_at,
            )
            .order_by("-visited_at")
            .limit(20)
            .values("visit_id", "visited_at")
        )

        if not prev_visits:
            return []

        prev_visit_ids = [v["visit_id"] for v in prev_visits]
        visit_date_map = {v["visit_id"]: v["visited_at"].date() for v in prev_visits}
        visit_order = {vid: i for i, vid in enumerate(prev_visit_ids)}

        field_rows = await OcrField.filter(
            ocr_result__ocr_job__visit_id__in=prev_visit_ids,
            ocr_result__ocr_job__hospital_id=actor.hospital_id,
            ocr_result__ocr_job__excluded_from_guide=False,
            is_confirmed=True,
        ).values(
            "field_type",
            "corrected_value",
            "extracted_value",
            "unit",
            "confirmed_at",
            visit_id="ocr_result__ocr_job__visit_id",
        )

        sorted_rows = sorted(
            field_rows,
            key=lambda r: (
                visit_order.get(r["visit_id"], 9999),
                -(r["confirmed_at"].timestamp() if r["confirmed_at"] else 0),
            ),
        )

        seen: set[str] = set()
        out: list[PreviousOcrFieldResponse] = []
        for row in sorted_rows:
            if row["field_type"] in seen:
                continue
            value = _resolved_value(row)
            if value is None:
                continue
            seen.add(row["field_type"])
            out.append(
                PreviousOcrFieldResponse(
                    field_type=row["field_type"],
                    value=value,
                    unit=row["unit"],
                    confirmed_at=row["confirmed_at"],
                    visit_date=visit_date_map[row["visit_id"]],
                )
            )

        return out

    async def finalize_ocr(self, visit_id: int, actor: OcrActor) -> Prescription:
        # 진료 소유권을 먼저 본다 — `generate()` 와 같은 차례다. 남의 병원
        # 진료는 「없다」로 답해야지 「확정이 아직 안 됐다」로 답하면 그 진료가
        # 있다는 사실이 새어 나간다.
        visit = await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id).first()
        if visit is None:
            raise OcrApiError(
                status.HTTP_404_NOT_FOUND,
                "VISIT_NOT_FOUND",
                "진료 건을 찾을 수 없습니다.",
            )

        # generate()와 동일한 기준 — assert_ocr_jobs_ready(app/ocr/utils.py).
        # PROCESSING job이 있으면 여기서 차단해 처방만 서고 안내문은
        # 영구 차단되는 진료가 생기는 것을 막는다 (KEY-271).
        # FAILED job은 안내 근거에서 제외하고 COMPLETED job만 사용한다.
        jobs = await assert_ocr_jobs_ready(visit_id, actor.hospital_id)

        results, doc_type_of = await _gather_results_from_jobs(jobs)
        if not results:
            raise _not_confirmed()

        fields_by_type: dict[str, OcrField] = merge_fields_by_type(results, doc_type_of=doc_type_of)

        if not fields_by_type:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "OCR_NOT_CONFIRMED",
                "확정된 OCR 항목이 없습니다.",
            )

        # **못 읽은 칸은 길을 막지 않는다** — 와이어프레임 S1-7 · KEY-271.
        #
        # 화면은 **값이 있는 항목만** 확정한다(`ocr-review.js` 의 `fieldsToConfirm`).
        # 빈 칸을 확정하면 그 빈 값이 안내문에 그대로 나가기 때문이다. 그래서
        # 「확인 완료」를 눌러도 못 읽은 칸은 미확정으로 남고, 화면은 그것을
        # 일부러 안 막는다(`generateBlocked` 가 `counts.missing` 을 안 본다).
        #
        # 여기서 **모든** 필드를 요구하면 판독이 한 칸이라도 못 읽은 진료는
        # 처방을 영영 못 세운다. 화면이 이 API 를 부르기 시작한 지금(KEY-271
        # 다리)은 그것이 곧 **안내문 자체를 못 만드는 것**이다. 푸는 길도 없다 —
        # 「이번 미시행」을 담을 칸이 서버에 없어 실서버에서는 버튼조차 안 그려진다.
        #
        # **값이 있는데 아무도 안 본 것**만 막는다. 그것이 확정의 뜻이다.
        # 여러 result에 걸쳐 미확정 필드를 확인한다.
        all_fields_flat = [f for r in results for f in r.fields]
        unconfirmed = read_but_unconfirmed(all_fields_flat)
        if unconfirmed is not None:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "OCR_NOT_CONFIRMED",
                "확정되지 않은 OCR 항목이 있습니다. 모든 항목을 먼저 확정해 주세요.",
            )

        ps_field = fields_by_type.get("PRESCRIPTION_SET")
        if ps_field is None or not ps_field.value:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "MISSING_PRESCRIPTION_SET",
                "처방 세트(PRESCRIPTION_SET) 필드가 없습니다.",
            )

        freq_field = fields_by_type.get("FREQUENCY")
        if freq_field is None or not freq_field.value:
            raise OcrApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "MISSING_FREQUENCY",
                "복용법(FREQUENCY) 필드가 없습니다.",
            )

        item_rows = _collect_item_rows(fields_by_type)

        async with in_transaction() as connection:
            # Visit 행을 먼저 잠가서 동시 finalize를 직렬화한다.
            # select_for_update()는 매칭 행이 없으면 락을 걸지 못하므로
            # 항상 존재하는 Visit을 진입점으로 쓴다 (guides.py 동일 패턴).
            if (
                await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
                .using_db(connection)
                .select_for_update()
                .first()
            ) is None:
                raise _not_found()

            prescription = await Prescription.filter(visit_id=visit_id).using_db(connection).first()
            if prescription is None:
                prescription = await Prescription.create(
                    visit_id=visit_id,
                    prescription_set=ps_field.value,
                    using_db=connection,
                )
            else:
                prescription.prescription_set = ps_field.value
                await prescription.save(update_fields=("prescription_set",), using_db=connection)

            await PrescriptionItem.filter(prescription_id=prescription.prescription_id).using_db(connection).delete()
            for name, frequency, duration_days in item_rows:
                await PrescriptionItem.create(
                    prescription=prescription,
                    name=name,
                    frequency=frequency,
                    duration_days=duration_days,
                    using_db=connection,
                )

        await prescription.fetch_related("items")
        return prescription


def serialize_job(job: OcrJob) -> OcrJobResponse:
    return OcrJobResponse(
        ocr_job_id=job.ocr_job_id,
        status=job.status,
        progress=job.progress,
        started_at=job.started_at,
        completed_at=job.completed_at,
        failure_code=job.failure_code,
        excluded_from_guide=job.excluded_from_guide,
    )


LOW_CONFIDENCE_THRESHOLD = 0.75
FIXTURE_MODEL_NAME = "fixture-v0"


async def seed_fixture_result(
    job: OcrJob,
    documents: list[tuple[int, OcrDocumentType]],
    connection: BaseDBAsyncClient,
) -> None:
    """fixture 결과를 DB에 기록하고 job을 COMPLETED로 전환한다 — 업로드 경로에서 job당 한 번 호출, 데모 전용.

    OcrResult.ocr_job 은 OneToOneField, OcrField 는 (ocr_result, field_type) unique 제약이 있으므로
    OcrDocumentText 는 문서마다 생성하고 OcrField 는 결과 전체에 하나만 만든다.
    """
    completed_at = now()
    result = await OcrResult.create(ocr_job=job, model_name=FIXTURE_MODEL_NAME, using_db=connection)
    first_doc_text = None
    for document_id, document_type in documents:
        doc_text = await OcrDocumentText.create(
            ocr_result=result,
            document_id=document_id,
            document_type=document_type,
            raw_text="[fixture] 합성 OCR 텍스트 — 실제 OCR 워커 연결 전 데모용 데이터",
            using_db=connection,
        )
        if first_doc_text is None:
            first_doc_text = doc_text
    await OcrField.create(
        ocr_result=result,
        document_text=first_doc_text,
        field_type="DIAGNOSIS",
        extracted_value="[fixture] 진단명",
        confidence=Decimal("0.85"),
        using_db=connection,
    )
    job.status = OcrJobStatus.COMPLETED
    job.progress = 100
    # 업로드 시 즉시 fixture를 심는 데모 경로에는 시작 시각이 없으므로 완료
    # 시각을 함께 기록한다. 반면 Worker가 실제 CLOVA를 시도한 뒤 fallback으로
    # 들어온 경우에는 이미 `started_at`이 있다. 그것을 덮어쓰면 처리시간이
    # 언제나 0ms가 되어 KEY-69 실행 증적이 사라진다.
    if job.started_at is None:
        job.started_at = completed_at
    job.completed_at = completed_at
    await job.save(
        update_fields=("status", "progress", "started_at", "completed_at"),
        using_db=connection,
    )


def _resolve_document_id(doc_text: OcrDocumentText | None) -> int | None:
    """원문 파기 후에는 None — document_id·source_line으로 원문 우회 노출 방지."""
    return doc_text.document_id if (doc_text is not None and doc_text.raw_text_purged_at is None) else None


def serialize_candidate(
    candidate: OcrFieldCandidate, doc_text_map: dict[int, OcrDocumentText] | None = None
) -> OcrCandidateResponse:
    confidence = float(candidate.confidence) if isinstance(candidate.confidence, Decimal) else candidate.confidence
    doc_text_map = doc_text_map or {}
    return OcrCandidateResponse(
        ocr_field_candidate_id=candidate.ocr_field_candidate_id,
        value=candidate.candidate_value,
        confidence=confidence,
        rank=candidate.rank,
        source_date=candidate.source_date,
        source_line=candidate.source_line,
        document_id=_resolve_document_id(
            doc_text_map.get(candidate.document_text_id) if candidate.document_text_id is not None else None
        ),
        is_selected=candidate.is_selected,
    )


def _serialize_candidates(field: OcrField, doc_text_map: dict[int, OcrDocumentText]) -> list[OcrCandidateResponse]:
    rel = getattr(field, "candidates", None)
    if rel is None or not getattr(rel, "_fetched", False):
        return []
    return [serialize_candidate(item, doc_text_map) for item in rel]


def serialize_field(field: OcrField, doc_text_map: dict[int, OcrDocumentText] | None = None) -> OcrFieldResponse:
    doc_text_map = doc_text_map or {}
    confidence = float(field.confidence) if isinstance(field.confidence, Decimal) else field.confidence
    return OcrFieldResponse(
        ocr_field_id=field.ocr_field_id,
        field_type=field.field_type,
        extracted_value=field.extracted_value,
        corrected_value=field.corrected_value,
        value=field.value,
        unit=field.unit,
        confidence=confidence,
        is_low_confidence=confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD,
        version=field.version,
        is_confirmed=field.is_confirmed,
        is_pending_report=field.is_pending_report,
        document_id=_resolve_document_id(
            doc_text_map.get(field.document_text_id) if field.document_text_id is not None else None
        ),
        source_line=field.source_line,
        modified_by=field.modified_by,
        modified_at=field.modified_at,
        confirmed_by=field.confirmed_by,
        confirmed_at=field.confirmed_at,
        candidates=_serialize_candidates(field, doc_text_map),
    )


class OcrService:
    def __init__(self, repository: OcrRepository) -> None:
        self.repository = repository

    async def job_for_visit(self, visit_id: int, actor: OcrActor) -> OcrJobResponse:
        job = await self.repository.get_latest_job_by_visit(visit_id, actor)
        if job is None:
            raise _not_found()
        return serialize_job(job)

    async def jobs_for_visit(self, visit_id: int, actor: OcrActor) -> list[OcrJobByDocumentResponse]:
        pairs = await self.repository.get_latest_jobs_by_document(visit_id, actor)
        return [
            OcrJobByDocumentResponse(
                document_id=jd.document_id,
                document_type=jd.document_type,
                ocr_job_id=job.ocr_job_id,
                status=job.status,
                progress=job.progress,
                started_at=job.started_at,
                completed_at=job.completed_at,
                failure_code=job.failure_code,
                excluded_from_guide=job.excluded_from_guide,
            )
            for jd, job in pairs
        ]

    async def status(self, ocr_job_id: str, actor: OcrActor) -> OcrJobResponse:
        return serialize_job(await self.repository.get_job(ocr_job_id, actor))

    async def result(self, ocr_job_id: str, actor: OcrActor) -> OcrResultResponse:
        result = await self.repository.get_result(ocr_job_id, actor)
        doc_text_map = {d.ocr_document_text_id: d for d in result.documents}
        return OcrResultResponse(
            ocr_result_id=result.ocr_result_id,
            ocr_job_id=result.ocr_job_id,
            model_name=result.model_name,
            model_version=result.model_version,
            version=result.version,
            confirmed_by=result.confirmed_by,
            confirmed_at=result.confirmed_at,
            documents=[
                OcrDocumentResponse(
                    document_id=item.document_id,
                    document_type=item.document_type,
                    raw_text=item.raw_text,
                    raw_text_purged_at=item.raw_text_purged_at,
                )
                for item in result.documents
            ],
            fields=[serialize_field(item, doc_text_map) for item in result.fields],
        )

    async def fields(self, ocr_job_id: str, actor: OcrActor, field_type: str | None) -> list[OcrFieldResponse]:
        fields, doc_texts = await self.repository.get_fields(ocr_job_id, actor, field_type)
        doc_text_map = {d.ocr_document_text_id: d for d in doc_texts}
        return [serialize_field(item, doc_text_map) for item in fields]

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> OcrFieldResponse:
        field, doc_texts = await self.repository.update_field(ocr_field_id, request, actor)
        doc_text_map = {d.ocr_document_text_id: d for d in doc_texts}
        return serialize_field(field, doc_text_map)

    async def write_field(
        self,
        visit_id: int,
        field_type: str,
        value: str | None,
        actor: OcrActor,
        unit: str | None = None,
    ) -> OcrFieldResponse | None:
        """판독이 못 읽은 값을 적어 넣는다. 비우면 지우고 `None` 을 준다."""
        field, doc_texts = await self.repository.write_field(visit_id, field_type, value, actor, unit=unit)
        if field is None:
            return None
        return serialize_field(field, {d.ocr_document_text_id: d for d in doc_texts})

    async def exclude_job(self, ocr_job_id: str, actor: OcrActor) -> OcrJobResponse:
        """잘못 올린 문서의 job을 안내 생성에서 제외한다 — 멱등 처리."""
        job = await self.repository.exclude_job(ocr_job_id, actor)
        return serialize_job(job)

    async def previous_fields(self, visit_id: int, actor: OcrActor) -> list[PreviousOcrFieldResponse]:
        """같은 환자·같은 병원의 이전 방문에서 확정된 OCR 값을 반환한다."""
        return await self.repository.get_previous_fields(visit_id, actor)

    async def finalize_ocr(self, visit_id: int, actor: OcrActor) -> FinalizeOcrResponse:
        """확정된 OcrField에서 Prescription·PrescriptionItem을 생성하거나 재확정한다."""
        prescription = await self.repository.finalize_ocr(visit_id, actor)
        return FinalizeOcrResponse(
            prescription_id=prescription.prescription_id,
            prescription_set=prescription.prescription_set,
            items=[
                PrescriptionItemResponse(
                    prescription_item_id=item.prescription_item_id,
                    name=item.name,
                    frequency=item.frequency,
                    duration_days=item.duration_days,
                )
                for item in prescription.items
            ],
        )
