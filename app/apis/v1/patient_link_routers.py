"""환자 링크·승인 안내 API — KEY-90, KEY-241, KEY-178."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, status

from app.dependencies.patient_auth import require_patient_session
from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.checkins import (
    CheckInAnswerContent,
    CheckInCreateRequest,
    CheckInPainResponse,
    CheckInPainTypeResponse,
    CheckInReadResponse,
    CheckInSaveResponse,
    HospitalCheckInResponse,
    PainType,
)
from app.dtos.patient_links import (
    GuidePageViewRequest,
    PatientCareBlockResponse,
    PatientCareResponse,
    PatientGuideDetailResponse,
    PatientGuideDrugResponse,
    PatientGuideGoalResponse,
    PatientGuideResponse,
    PatientGuideSectionResponse,
    PatientLifeAxisResponse,
    PatientLifeResponse,
    PatientLinkIssueResponse,
    PatientMedicationStatResponse,
)
from app.models.visits import CheckIn, CheckInMedication, GuideDocument, GuideSectionKey, PatientGuideLink
from app.services.checkins import CheckInService, approved_answer_bodies
from app.services.patient_links import PatientGuideData, PatientLinkService
from app.services.patient_usage import PatientUsageService

patient_link_management_router = APIRouter(prefix="/visits", tags=["patient-links"])
patient_guide_router = APIRouter(prefix="/guides", tags=["patient-guides"])
patient_checkin_router = APIRouter(prefix="/checkins", tags=["patient-checkins"])


def _service() -> PatientLinkService:
    return PatientLinkService()


def _usage_service() -> PatientUsageService:
    return PatientUsageService()


def _checkin_service() -> CheckInService:
    return CheckInService()


@patient_link_management_router.post(
    "/{visit_id}/guide/link",
    response_model=PatientLinkIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_patient_guide_link(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[PatientLinkService, Depends(_service)],
) -> PatientLinkIssueResponse:
    link, raw_token = await service.issue(actor, visit_id)
    return PatientLinkIssueResponse(
        path=f"/api/v1/guides/{raw_token}",
        expires_at=link.expires_at,
    )


def _patient_response(
    link: PatientGuideLink,
    guide: GuideDocument,
    data: PatientGuideData,
) -> PatientGuideResponse:
    if guide.approved_at is None:
        # 서비스가 앞에서 막아야 하는 불변식이다. 최적화 모드에서 사라지는
        # assert에 응답 안전을 맡기지 않는다.
        raise RuntimeError("approved guide has no approved_at")

    medication_body = data.sections.get(GuideSectionKey.MEDICATION)
    caution_body = data.sections.get(GuideSectionKey.CAUTION)
    emergency_body = data.sections.get(GuideSectionKey.EMERGENCY)
    life_body = data.sections.get(GuideSectionKey.LIFE)
    medication = data.medication
    progress = medication.progress if medication is not None else None

    stat = (
        PatientMedicationStatResponse(
            drug_name=medication.drug_name,
            drug_sub=medication.stat_sub,
            prescribed=medication.prescribed,
            day_on=progress.day_on if progress is not None else None,
            remaining=progress.remaining if progress is not None else None,
            pct=progress.pct if progress is not None else None,
            out=(
                f"ⓘ {progress.depletion_date.month}월 {progress.depletion_date.day}일경 약이 소진돼요"
                if progress is not None
                else None
            ),
            why=medication_body,
        )
        if medication is not None
        else None
    )
    guide_detail = (
        PatientGuideDetailResponse(
            summary=medication_body,
            goals=[
                PatientGuideGoalResponse(
                    n=goal.name,
                    now=goal.current,
                    t=goal.target,
                    has_chart=goal.has_chart,
                    range_label=goal.range_label,
                )
                for goal in data.goals
            ],
            drug=(
                PatientGuideDrugResponse(
                    n=medication.drug_name,
                    s=medication.ingredient_label,
                    d=medication.directions,
                )
                if medication is not None
                else None
            ),
            why=[medication_body] if medication_body else [],
            how=medication.directions if medication is not None else None,
            # `messages`는 병원 안내/발송 행정 문구다. 전용 재진 계획 소스가
            # 생기기 전에는 P2의 `next`로 의미를 바꿔 내보내지 않는다.
            next=None,
        )
        if medication_body or medication is not None or data.goals
        else None
    )
    care = (
        PatientCareResponse(
            blocks=[PatientCareBlockResponse(t="주의사항", p=[caution_body])] if caution_body else [],
            danger=[emergency_body] if emergency_body else [],
            # 일반 병원 안내를 증상별 문의 기준으로 오해시키지 않는다.
            ask=None,
        )
        if caution_body or emergency_body
        else None
    )
    life = (
        PatientLifeResponse(
            sub=data.disease_name,
            axes={
                "생활관리": PatientLifeAxisResponse(
                    title="생활관리",
                    p=[life_body],
                )
            }
            if life_body
            else {},
        )
        if life_body or data.disease_name
        else None
    )
    return PatientGuideResponse(
        version=guide.version,
        approved_at=guide.approved_at,
        expires_at=link.expires_at,
        sections=[
            PatientGuideSectionResponse(key=section.section_key, body=section.body)
            for section in sorted(guide.sections, key=lambda item: item.guide_section_id)
        ],
        visit=data.visit_date.strftime("%Y.%m.%d"),
        clinic=data.clinic_name,
        disease=data.disease_name,
        stat=stat,
        guide=guide_detail,
        care=care,
        life=life,
    )


async def _guide_data(
    token: str,
    service: Annotated[PatientLinkService, Depends(_service)],
) -> tuple[PatientGuideLink, GuideDocument, PatientGuideData]:
    return await service.get_patient_guide_data(token)


@patient_guide_router.get(
    "/{token}",
    response_model=PatientGuideResponse,
    response_model_exclude_none=True,
)
async def read_patient_guide(
    guide_data: Annotated[tuple[PatientGuideLink, GuideDocument, PatientGuideData], Depends(_guide_data)],
    # 링크 자체가 유효한지 위 _guide_data 에서 먼저 확인한다. 세션 체크를
    # 먼저 하면 만료·폐기된 링크도 401(세션 없음)로 가려져서 기존 410/404
    # 계약이 깨진다 — 그래서 순서가 중요하다 (KEY-178).
    _session: Annotated[None, Depends(require_patient_session)],
    usage: Annotated[PatientUsageService, Depends(_usage_service)],
) -> PatientGuideResponse:
    link, guide, data = guide_data
    # 승인 확인을 통과한 뒤에 남긴다 (KEY-170).
    # 지금은 **같은 요청 안에서** 남기므로, 기록이 실패하면 열람도 실패한다.
    # 통계가 환자의 안내 열람을 막는 모양이라 KEY-95·KEY-96 에서 챗봇 호출부가
    # 붙을 때 분리 여부를 다시 본다.
    await usage.record_guide_view(guide.guide_document_id)
    return _patient_response(link, guide, data)


@patient_guide_router.post("/{token}/views", status_code=204)
async def record_guide_page_view(
    token: str,
    payload: GuidePageViewRequest,
    service: Annotated[PatientLinkService, Depends(_service)],
    usage: Annotated[PatientUsageService, Depends(_usage_service)],
) -> None:
    """환자가 안내문의 **한 장**을 열었다 — KEY-256, 원문 S2-2·D1-6.

    링크로 들어오는 `GET /{token}` 은 안내문을 통째로 내려 주고, 환자 화면은
    탭을 **브라우저 안에서만** 넘긴다. 그래서 서버에는 「열었다」한 줄만 남고
    「어디까지 읽었나」가 없었다. 스탭은 다 읽은 환자와 첫 장만 열고 닫은
    환자를 구별할 수 없었는데, 다음 진료 때 물을 것이 서로 다르다.

    **본문에 원문이 없다.** 어느 장을 열었는지 하나뿐이다 — 이 저장소가
    이용 기록에 두는 선(`app/services/patient_usage.py`)을 그대로 지킨다.

    **`204` 로 답한다.** 환자 화면이 받을 것이 없다. 그리고 이 호출이 실패해도
    화면은 계속 읽혀야 한다 — 통계가 환자의 안내 열람을 막으면 안 된다.
    같은 이유로 화면 쪽은 이 호출을 기다리지 않는다.
    """
    _, guide, _ = await service.get_patient_guide_data(token)
    await usage.record_guide_view(guide.guide_document_id, section=payload.section)


def _pain_response(check_in: CheckIn) -> CheckInPainResponse | None:
    if check_in.pain_had is None:
        return None
    return CheckInPainResponse(
        had=check_in.pain_had,
        score=check_in.pain_score,
        types=[cast(PainType, item) for item in check_in.pain_types],
    )


async def _checkin_form_data(
    token: str,
    service: Annotated[CheckInService, Depends(_checkin_service)],
) -> tuple[GuideDocument, bool]:
    return await service.read_form(token)


@patient_checkin_router.get("/{token}", response_model=CheckInReadResponse)
async def read_patient_checkin(
    form_data: Annotated[tuple[GuideDocument, bool], Depends(_checkin_form_data)],
    # read_patient_guide 와 같은 이유로 순서가 중요하다 (KEY-178).
    _session: Annotated[None, Depends(require_patient_session)],
) -> CheckInReadResponse:
    guide, answered = form_data
    medication, caution = approved_answer_bodies(guide)
    return CheckInReadResponse(
        answers={
            CheckInMedication.TAKING: None,
            CheckInMedication.UNCOMFORTABLE: CheckInAnswerContent(lead=caution),
            CheckInMedication.MISSING: CheckInAnswerContent(lead=medication),
            CheckInMedication.STOPPED_SIDE_EFFECT: CheckInAnswerContent(lead=caution),
            CheckInMedication.STOPPED_IMPROVED: CheckInAnswerContent(lead=medication),
        },
        pain_types=[
            CheckInPainTypeResponse(key="menstrual", label="월경통"),
            CheckInPainTypeResponse(key="intercourse", label="성교통"),
            CheckInPainTypeResponse(key="defecation", label="배변통"),
            CheckInPainTypeResponse(key="chronic_pelvic", label="만성골반통"),
        ],
        answered=answered,
    )


@patient_checkin_router.post("/{token}", response_model=CheckInSaveResponse, status_code=status.HTTP_201_CREATED)
async def save_patient_checkin(
    token: str,
    payload: CheckInCreateRequest,
    _: Annotated[None, Depends(require_patient_session)],
    service: Annotated[CheckInService, Depends(_checkin_service)],
) -> CheckInSaveResponse:
    check_in = await service.save(token, payload)
    return CheckInSaveResponse(
        check_in_id=check_in.check_in_id,
        medication=check_in.medication,
        pain=_pain_response(check_in),
    )


@patient_link_management_router.get("/{visit_id}/checkin", response_model=HospitalCheckInResponse)
async def read_hospital_checkin(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[CheckInService, Depends(_checkin_service)],
) -> HospitalCheckInResponse:
    check_in = await service.get_for_hospital(actor, visit_id)
    return HospitalCheckInResponse(
        check_in_id=check_in.check_in_id,
        visit_id=visit_id,
        medication=check_in.medication,
        pain=_pain_response(check_in),
        submitted_at=check_in.created_at,
    )
