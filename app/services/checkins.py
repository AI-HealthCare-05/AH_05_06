"""승인 안내 링크에 연결된 D+7 응답 저장·조회 — KEY-151."""

from tortoise.exceptions import IntegrityError

from app.core.auth_errors import AuthError as ApiError
from app.dtos.checkins import CheckInCreateRequest
from app.models.visits import CheckIn, GuideDocument, GuideSectionKey
from app.services.patient_links import PatientLinkService

HOSPITAL_ROLES = frozenset({"staff", "doctor"})


def _checkin_not_found() -> ApiError:
    return ApiError("CHECKIN_NOT_FOUND", 404, "D+7 응답을 찾을 수 없습니다.")


class CheckInService:
    def __init__(self, links: PatientLinkService | None = None) -> None:
        self.links = links or PatientLinkService()

    async def read_form(self, raw_token: str) -> tuple[GuideDocument, bool]:
        _, guide = await self.links.get_approved_guide(raw_token)
        answered = await CheckIn.filter(guide_document_id=guide.guide_document_id).exists()
        return guide, answered

    async def save(self, raw_token: str, payload: CheckInCreateRequest) -> CheckIn:
        _, guide = await self.links.get_approved_guide(raw_token)
        pain = payload.pain
        try:
            return await CheckIn.create(
                guide_document=guide,
                medication=payload.medication,
                pain_had=pain.had if pain is not None else None,
                pain_score=pain.score if pain is not None else None,
                pain_types=list(pain.types) if pain is not None else [],
            )
        except IntegrityError as exc:
            raise ApiError("CHECKIN_ALREADY_ANSWERED", 409, "이미 저장된 D+7 응답입니다.") from exc

    async def get_for_hospital(self, actor, visit_id: int) -> CheckIn:
        if not HOSPITAL_ROLES.intersection(actor.roles):
            raise ApiError("FORBIDDEN", 403, "D+7 응답을 조회할 권한이 없습니다.")
        check_in = await CheckIn.filter(
            guide_document__visit_id=visit_id,
            guide_document__visit__hospital_id=actor.hospital_id,
        ).first()
        if check_in is None:
            # 없는 진료·타 병원 진료·아직 응답하지 않은 진료를 같은 응답으로 감춘다.
            raise _checkin_not_found()
        return check_in


def approved_answer_bodies(guide: GuideDocument) -> tuple[str, str]:
    """D+7 화면에 새 의료 문장을 만들지 않고 승인 섹션만 재사용한다."""

    sections = {section.section_key: section.body for section in guide.sections}
    medication = sections.get(GuideSectionKey.MEDICATION)
    if not medication:
        # 최소 시나리오의 승인 섹션 한 개조차 없으면 새 문장을 만들어 채우지 않는다.
        raise ApiError("GUIDE_CONTENT_INCOMPLETE", 409, "D+7 확인에 필요한 승인 안내가 없습니다.")
    caution = sections.get(GuideSectionKey.CAUTION) or medication
    return medication, caution
