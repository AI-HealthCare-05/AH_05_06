"""승인 안내 링크에 연결된 D+7 응답 저장·조회 — KEY-151."""

from tortoise.exceptions import IntegrityError

from app.core.auth_errors import AuthError as ApiError
from app.dtos.checkins import CheckInCreateRequest
from app.models.visits import CheckIn, GuideDocument, GuideSectionKey
from app.services.patient_links import PatientLinkService

HOSPITAL_ROLES = frozenset({"staff", "doctor"})


def _checkin_not_found() -> ApiError:
    return ApiError("CHECKIN_NOT_FOUND", 404, "D+7 응답을 찾을 수 없습니다.")


def _answer_conflict() -> ApiError:
    """**같은 답이 아니라 다른 답이 왔을 때만** 막는다 — KEY-335.

    「복용 중」으로 저장해 놓고 나중에 「중단」이 오면 조용히 덮으면 안 된다.
    어느 쪽이 환자의 뜻인지 서버가 모른다.
    """
    return ApiError("CHECKIN_ALREADY_ANSWERED", 409, "이미 저장된 답과 다른 내용입니다.")


def _same_answer(existing: CheckIn, payload: CheckInCreateRequest) -> bool:
    """저장된 줄과 이번 요청이 **같은 답**인가 — KEY-335.

    🚩 `pain_types` 는 **집합으로** 본다. 화면이 체크박스라 고른 차례가 그대로
    실려 오는데, 순서까지 따지면 **같은 답인데 conflict** 가 난다 — 고치려던
    문제를 다시 만드는 셈이다. 중복은 `CheckInPainRequest` 가 이미 막는다.

    `pain` 이 아예 없는 것(`None`)과 「통증 없음」(`had=False`)은 **다른 답**이다.
    앞엣것은 안 물어본 것이고 뒤엣것은 없다고 답한 것이라, `pain_had` 가
    `None` 이냐 `False` 냐로 갈린다.
    """
    pain = payload.pain
    return (
        existing.medication == payload.medication
        and existing.pain_had == (pain.had if pain is not None else None)
        and existing.pain_score == (pain.score if pain is not None else None)
        and set(existing.pain_types or []) == set(pain.types if pain is not None else [])
    )


class CheckInService:
    def __init__(self, links: PatientLinkService | None = None) -> None:
        self.links = links or PatientLinkService()

    async def read_form(self, raw_token: str) -> tuple[GuideDocument, bool]:
        _, guide = await self.links.get_approved_guide(raw_token)
        answered = await CheckIn.filter(guide_document_id=guide.guide_document_id).exists()
        return guide, answered

    async def save(self, raw_token: str, payload: CheckInCreateRequest) -> CheckIn:
        """D+7 답을 저장한다. **같은 답을 다시 보내면 그때 그 줄을 돌려준다** (KEY-335).

        예전에는 두 번째가 무조건 `409` 였다. 그런데 **저장은 이미 성공한 뒤**라,
        두 번 누르거나 응답이 유실돼 다시 시도한 환자는 **된 일을 실패로 본다.**
        D+7 화면은 한 번 열고 마는 자리여서, 거기서 오류를 보면 그대로 닫는다.

        환자 피드백(`patient_feedback.py::_same_or_conflict`)이 같은 문제를 이미
        같은 모양으로 푼다.
        """
        _, guide = await self.links.get_approved_guide(raw_token)

        existing = await CheckIn.filter(guide_document_id=guide.guide_document_id).first()
        if existing is not None:
            return self._same_or_conflict(existing, payload)

        pain = payload.pain
        try:
            return await CheckIn.create(
                guide_document=guide,
                medication=payload.medication,
                pain_had=pain.had if pain is not None else None,
                pain_score=pain.score if pain is not None else None,
                pain_types=list(pain.types) if pain is not None else [],
            )
        except IntegrityError:
            # 위에서 읽은 뒤 `create` 사이에 다른 요청이 먼저 넣었다 — 두 번
            # 누름이 거의 동시에 온 자리다. DB 가 막아 준 것을 그대로 두고
            # 다시 읽어, 같은 답이면 성공으로 돌려준다.
            existing = await CheckIn.filter(guide_document_id=guide.guide_document_id).first()
            if existing is None:
                raise
            return self._same_or_conflict(existing, payload)

    @staticmethod
    def _same_or_conflict(existing: CheckIn, payload: CheckInCreateRequest) -> CheckIn:
        if not _same_answer(existing, payload):
            raise _answer_conflict()
        return existing

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
