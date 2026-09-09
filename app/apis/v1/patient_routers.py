from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.api_errors import ApiError, ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read, require_patient_write
from app.dtos.base import CursorPage
from app.dtos.patient_history import PatientHistoryResponse
from app.dtos.patients import (
    LatestVisitResponse,
    PatientCategory,
    PatientCreateRequest,
    PatientListItem,
    PatientListResponse,
    PatientResponse,
    PatientUpdateRequest,
    RosterPage,
)
from app.dtos.visits import DoctorResponse
from app.services.patient_history import DEFAULT_VISITS, PatientHistoryService
from app.services.patients import PatientService

patient_router = APIRouter(prefix="/patients", tags=["patients"], route_class=ContractRoute)


@patient_router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    data: PatientCreateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[PatientService, Depends(PatientService)],
) -> PatientResponse:
    return PatientResponse.model_validate(await service.create(actor, data))


@patient_router.get("", response_model=PatientListResponse)
async def list_patients(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[PatientService, Depends(PatientService)],
    keyword: str | None = None,
    category: PatientCategory = PatientCategory.ALL,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PatientListResponse:
    """환자 명단.

    **자리를 옮기는 말은 둘 중 하나만 쓴다.** `cursor` 는 등록 화면의 찾기가
    쓰는 「이 뒤로 더」이고, `offset` 은 환자 관리 표가 쓰는 「몇 쪽」이다
    (KEY-303). 둘을 함께 주면 `patient_id > cursor` 를 건 **뒤에** 다시
    `offset` 만큼 건너뛰어, 부른 사람이 뜻하지 않은 자리가 나온다. 조용히
    한쪽을 이기게 두면 그 어긋남이 화면에서야 드러난다 — 여기서 운다.
    """
    if cursor is not None and offset:
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "cursor 와 offset 은 함께 쓸 수 없습니다. 하나만 보내 주세요.",
            [
                {"field": "cursor", "message": "이어 보기(cursor)와 쪽 이동(offset) 중 하나만 씁니다"},
                {"field": "offset", "message": "이어 보기(cursor)와 쪽 이동(offset) 중 하나만 씁니다"},
            ],
        )

    rows, counts, next_cursor, has_next, total = await service.list(
        actor,
        keyword=keyword,
        category=category,
        cursor=cursor,
        limit=limit,
        offset=offset,
    )
    items = []
    for row in rows:
        response = PatientListItem.model_validate(row.patient)
        if row.latest_visit is not None:
            response.latest_visit = LatestVisitResponse.model_validate(row.latest_visit)
        response.diagnosis_name = row.diagnosis_name
        response.doctor = DoctorResponse(doctor_id=row.doctor.staff_id, name=row.doctor.name) if row.doctor else None
        response.work_category = row.work_category
        response.detail_status = row.detail_status
        response.flags = row.flags
        items.append(response)
    return PatientListResponse(
        counts=counts,
        selected_category=category,
        items=items,
        page=CursorPage(next_cursor=next_cursor, has_next=has_next),
        roster=RosterPage(offset=offset, limit=limit, total=total, has_next=has_next),
    )


@patient_router.get("/{patient_id}/history", response_model=PatientHistoryResponse)
async def read_patient_history(
    patient_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[PatientHistoryService, Depends(PatientHistoryService)],
    limit: Annotated[int, Query(ge=1, le=20)] = DEFAULT_VISITS,
) -> PatientHistoryResponse:
    """환자 이력 — 와이어프레임 S2-2.

    **스탭 · 의사 공통이다.** 원문 주석이 층을 못박는다 — 관리에 필요한
    만큼(발송 · 열람 · 응답)은 여기서 둘 다 보고, 감사 수준(누가 열어봤나 ·
    토큰 · 버전 이력)은 어드민 A1-7 로 관리자에게만 간다.
    """
    found = await service.read(actor, patient_id, limit=limit)
    return PatientHistoryResponse(
        patient_id=found.patient.patient_id,
        name=found.patient.name,
        hospital_patient_no=found.patient.hospital_patient_no,
        phone=found.patient.phone,
        diagnosis_name=found.diagnosis_name,
        doctor=(DoctorResponse(doctor_id=found.doctor.staff_id, name=found.doctor.name) if found.doctor else None),
        visits=found.visits,
        total=found.total,
    )


@patient_router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
    service: Annotated[PatientService, Depends(PatientService)],
) -> PatientResponse:
    return PatientResponse.model_validate(await service.get(actor, patient_id))


@patient_router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    data: PatientUpdateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_write)],
    service: Annotated[PatientService, Depends(PatientService)],
) -> PatientResponse:
    return PatientResponse.model_validate(await service.update(actor, patient_id, data))
