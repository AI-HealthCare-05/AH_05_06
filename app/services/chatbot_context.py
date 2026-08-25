"""승인 완료 안내 → 챗봇 컨텍스트 변환 — KEY-89.

구현 가능 범위
  - 토큰 기반 승인·만료·유효성 차단 (PatientLinkService 위임)
  - 승인 섹션 본문 → ContextSection 변환
  - clinic_name (Hospital.name 직접 조회)
  - encounter_date (Visit.visited_at 파생)

PR 제한사항 — 미구현 필드
  - medications : PrescriptionItem 에 ingredient·strength·purpose·instructions 없음
  - knowledge   : ApprovedKnowledge 의 title·source_label·kind 생성 규칙 미확정
                  (김고은과 인터페이스 합의 후 KEY-96 에서 연결)
  - next_visit_date : Visit 모델에 다음 진료일 필드 없음
  - GuidanceSection.title / source_label : GuideSection 모델에 없는 필드
  - messages 섹션 : 행정 문구라 챗봇 컨텍스트에서 제외
"""

from dataclasses import dataclass
from datetime import date, datetime

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

    PR #18 의 ApprovedGuidanceBundle 과의 차이는 PR 본문 제한사항 절에 기록한다.
    소비자(KEY-96 챗봇 엔드포인트)가 붙을 때 필드를 추가한다.
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
    """

    async def get_context(self, raw_token: str) -> ApprovedChatbotContext:
        _, guide = await PatientLinkService().get_approved_guide(raw_token)
        hospital = await Hospital.get(hospital_id=guide.hospital_id)
        await guide.fetch_related("visit")
        return _to_context(guide, hospital.name, guide.visit.visited_at.date())


def _to_context(
    guide: GuideDocument,
    clinic_name: str,
    encounter_date: date,
) -> ApprovedChatbotContext:
    section_map = {s.section_key: s for s in guide.sections}

    def _pick(*keys: GuideSectionKey) -> list[ContextSection]:
        return [ContextSection(key=key.value, body=section_map[key].body) for key in keys if key in section_map]

    return ApprovedChatbotContext(
        guide_document_id=guide.guide_document_id,
        visit_id=guide.visit_id,
        approved_at=guide.approved_at,  # type: ignore[arg-type]
        clinic_name=clinic_name,
        encounter_date=encounter_date,
        medication_sections=_pick(GuideSectionKey.MEDICATION),
        caution_sections=_pick(GuideSectionKey.CAUTION, GuideSectionKey.EMERGENCY),
        lifestyle_sections=_pick(GuideSectionKey.LIFE),
    )
