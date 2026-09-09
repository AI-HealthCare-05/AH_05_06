"""환자 화면이 받는 파생을 **한 곳에서** 짓는다 — KEY-294.

스탭·의사의 「환자 화면 미리보기」(`GET /visits/{id}/guide`)와 환자
종점(`GET /p/{token}`)이 같은 카드를 그린다. 두 곳에서 따로 지으면 미리보기가
「환자가 받는 그대로」라고 적어 놓고 다른 것을 보이게 된다 — KEY-286 이
없애려던 바로 그 거짓이다.

여기 있는 것은 **모양을 바꾸는 일**뿐이다. 값을 읽어 오는 것은
`PatientLinkService.build_patient_guide_data()` 하나이고, 승인·만료 게이트는
부르는 쪽이 각자 친다 — 환자는 승인된 것만 보고, 스탭은 승인 전에도 본다.
"""

from app.dtos.patient_links import (
    PatientGuideDetailResponse,
    PatientGuideDrugResponse,
    PatientGuideGoalResponse,
    PatientMedicationStatResponse,
)
from app.models.visits import GuideSectionKey
from app.services.patient_links import PatientGuideData


def medication_stat_of(data: PatientGuideData) -> PatientMedicationStatResponse | None:
    """현황(P1)의 복약 진행 카드. 처방이 없으면 카드가 아예 안 선다."""
    medication = data.medication
    if medication is None:
        return None

    progress = medication.progress
    return PatientMedicationStatResponse(
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
        why=data.sections.get(GuideSectionKey.MEDICATION),
    )


def guide_detail_of(data: PatientGuideData) -> PatientGuideDetailResponse | None:
    """복약지도(P2)의 카드들 — 오늘 진료 요약 · 나의 목표 · 처방받은 약 · 복용 방법.

    **값이 없는 카드는 안 세운다.** 환자 렌더러가 `if (g.drug)` · `if (g.how)` ·
    `if (g.next)` 로 그렇게 하므로, 여기서 빈 껍데기를 만들면 미리보기만 환자와
    달라진다.
    """
    medication = data.medication
    medication_body = data.sections.get(GuideSectionKey.MEDICATION)
    if not medication_body and medication is None and not data.goals:
        return None

    return PatientGuideDetailResponse(
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
