"""환자 이용 이벤트 기록 — KEY-170.

KEY-143 의 환류 기반이다. 「몇 명이 안내를 열었나 · 무엇을 주로 묻나 ·
얼마나 막히나」를 세려면 그 결과가 남아야 한다.

이 모듈의 규칙은 하나다 — **원문을 받지 않는다.**

`record_chatbot_answer()` 의 인자에 질문·답변·프롬프트를 넣을 자리가 없다.
넣을 수 있게 두면 언젠가 누가 넣고, 그때는 이미 DB 에 쌓인 뒤다. 갈래
(`PatientQuestionKind`)와 결과(`PatientAnswerOutcome`)만 받는다.

KEY-96(승인 컨텍스트 기반 LLM)의 `ChatbotService._record()`가 이
인터페이스를 호출한다. 챗봇 질문·답변 원문 대신 아래에서 제한한 갈래와
결과만 저장한다.
"""

from app.core.auth_errors import AuthError as ApiError
from app.models.visits import (
    GuideDocument,
    GuideSectionKey,
    GuideStatus,
    PatientAnswerOutcome,
    PatientQuestionKind,
    PatientUsageEvent,
    PatientUsageEventType,
)


def _not_recordable() -> ApiError:
    """**왜 못 남기는지 환자에게 알려 주지 않는다.**

    「없는 안내문」과 「아직 승인 안 된 안내문」을 가르면, 그 차이만으로
    「그 진료가 있다」를 알 수 있다. 이벤트 기록은 환자 화면이 부르는 자리라
    같은 답을 준다.
    """
    return ApiError("GUIDE_NOT_FOUND", 404, "안내문을 찾을 수 없습니다.")


class PatientUsageService:
    """열람·챗봇 결과를 남기는 **한 곳**.

    KEY-95·KEY-96 이 각자 `PatientUsageEvent.create()` 를 부르면, 「승인된
    안내문에만 남긴다」 같은 규칙이 두 곳에 복제된다. 규칙을 여기 모은다.
    """

    @staticmethod
    async def _approved(guide_document_id: int) -> GuideDocument:
        guide = await GuideDocument.filter(guide_document_id=guide_document_id).first()
        if guide is None:
            raise _not_recordable()
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            # 승인 전 안내문에는 이용 이벤트가 생길 수 없다 — 환자가 볼 수
            # 없는 글이다. 여기서 막지 않으면 「아직 안 나간 글을 환자가
            # 읽었다」는 줄이 통계에 섞인다.
            raise _not_recordable()
        return guide

    async def record_guide_view(self, guide_document_id: int) -> PatientUsageEvent:
        """환자가 승인 안내를 열었다."""
        guide = await self._approved(guide_document_id)
        return await PatientUsageEvent.create(
            guide_document=guide,
            event_type=PatientUsageEventType.GUIDE_VIEWED,
        )

    async def record_chatbot_answer(
        self,
        guide_document_id: int,
        *,
        question_kind: PatientQuestionKind,
        outcome: PatientAnswerOutcome,
        grounded_section: GuideSectionKey | None = None,
        response_ref_digest: str | None = None,
    ) -> PatientUsageEvent:
        """챗봇이 답했다 · 막았다 · 못 했다.

        **인자에 원문이 없다.** 갈래와 결과, 그리고 어느 갈래를 근거로 삼았는지
        까지다. `grounded_section` 도 「어디를 봤나」이지 그 본문이 아니다.

        키워드 인자로만 받는 것은 순서를 헷갈려 갈래와 결과가 바뀌는 것을
        막으려는 것이다 — 둘 다 문자열이라 바뀌어도 조용히 저장된다.
        """
        guide = await self._approved(guide_document_id)
        return await PatientUsageEvent.create(
            guide_document=guide,
            event_type=PatientUsageEventType.CHATBOT_ANSWERED,
            question_kind=question_kind,
            answer_outcome=outcome,
            grounded_section=grounded_section,
            response_ref_digest=response_ref_digest,
        )
