"""승인 완료 안내 → 챗봇 컨텍스트 변환 — KEY-89.

구현 가능 범위
  - 토큰 기반 승인·만료·유효성 차단 (PatientLinkService 위임)
  - 승인 섹션 본문 → ContextSection 변환
  - clinic_name (Hospital.name 직접 조회)
  - encounter_date (Visit.visited_at 파생)

미구현 필드 — KEY-88 계약 기준으로 이희진·김고은과 합의 후 추가
  - medications : PrescriptionItem 에 ingredient·strength·purpose·instructions 없음
  - knowledge   : ApprovedKnowledge 의 title·source_label·kind 생성 규칙 미확정
  - next_visit_date : Visit 모델에 다음 진료일 필드 없음
  - GuidanceSection.title / source_label : GuideSection 모델에 없는 필드
  - messages 섹션 : 행정 문구라 챗봇 컨텍스트에서 제외
"""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.time import DISPLAY_TIMEZONE
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideSectionKey
from app.services.patient_links import PatientLinkService


@dataclass(frozen=True)
class ContextSection:
    key: str
    body: str


@dataclass(frozen=True)
class ApprovedChatbotContext:
    """현재 구현 가능한 범위의 챗봇 컨텍스트.

    미구현 필드는 모듈 docstring 참조.
    필드 추가가 필요하면 KEY-88 계약을 기준으로 이희진·김고은과 합의 후 진행한다.
    """

    guide_document_id: int
    visit_id: int
    approved_at: datetime
    clinic_name: str
    encounter_date: date
    medication_sections: list[ContextSection]
    caution_sections: list[ContextSection]  # caution → emergency 순
    lifestyle_sections: list[ContextSection]


class ChatbotContextService:
    """토큰을 받아 승인 안내를 챗봇 컨텍스트로 변환한다.

    승인·만료·토큰 검증은 PatientLinkService 에 위임한다.
    sections 는 get_approved_guide 내부의 prefetch_related 로 이미 로드된다.

    KEY-88 필드 합의(이희진·김고은) 전까지는 프로덕션에서 아직 호출되지 않는다.
    """

    async def get_context(self, raw_token: str) -> ApprovedChatbotContext:
        _, guide = await PatientLinkService().get_approved_guide(raw_token)
        hospital = await Hospital.get(hospital_id=guide.hospital_id)
        await guide.fetch_related("visit")
        if guide.approved_at is None:
            raise RuntimeError("approved guide has no approved_at")
        # **좁힌 값을 직접 넘긴다.** `guide` 통째로 넘기면 위에서 확인한 것이
        # 문 밖에서 풀려, 「승인됐는데 승인 시각이 없다」를 아무도 다시 안 본다.
        return _to_context(
            guide,
            guide.approved_at,
            hospital.name,
            guide.visit.visited_at.astimezone(DISPLAY_TIMEZONE).date(),
        )


def _to_context(
    guide: GuideDocument,
    approved_at: datetime,
    clinic_name: str,
    encounter_date: date,
) -> ApprovedChatbotContext:
    section_map = {s.section_key: s for s in guide.sections}

    def _pick(*keys: GuideSectionKey) -> list[ContextSection]:
        return [ContextSection(key=key.value, body=section_map[key].body) for key in keys if key in section_map]

    return ApprovedChatbotContext(
        guide_document_id=guide.guide_document_id,
        visit_id=guide.visit_id,
        approved_at=approved_at,
        clinic_name=clinic_name,
        encounter_date=encounter_date,
        medication_sections=_pick(GuideSectionKey.MEDICATION),
        caution_sections=_pick(GuideSectionKey.CAUTION, GuideSectionKey.EMERGENCY),
        lifestyle_sections=_pick(GuideSectionKey.LIFE),
    )
