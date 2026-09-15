"""챗봇 원문 일치·질문 분류 판정 규칙 — KEY-351.

모델 호출 없이 순수 함수만 잰다. KEY-279 2차 패스에서 발견된 두 원인을
각각 재현하고 고정한다:

① `_is_extractively_grounded()`가 답 전체를 본문의 연속된 부분 문자열로
   요구해서, 모델이 원문 문장을 그대로 쓰고도 순서만 바꾸면 막혔다.
② `classify_question()`이 "주의"를 못 알아들어 「주의사항이 뭐죠?」가
   OTHER로 빠지고, 조사 포함 토큰 겹침 계산이 안 맞아 섹션을 못 찾았다.

안전 원칙(승인 안내 밖의 새 문장·진단·복약 중단/변경 권고는 계속 막는다)
은 회귀 테스트로 같이 고정한다.
"""

from app.models.visits import GuideSectionKey, PatientQuestionKind
from app.services.chatbot import (
    ApprovedContext,
    _is_extractively_grounded,
    classify_question,
    select_approved_context,
)


class _Section:
    """`select_approved_context()`가 보는 최소 계약 — `GuideSection`을
    안 만들고(DB 필요) 순수 함수만 잰다."""

    def __init__(self, section_key: GuideSectionKey, body: str, guide_section_id: int) -> None:
        self.section_key = section_key
        self.body = body
        self.guide_section_id = guide_section_id


MEDICATION_BODY = "이 약은 하루 세 번, 식후 30분에 복용하세요. 술과 함께 복용하지 마세요."
CAUTION_BODY = "이 약을 복용하는 동안 술을 마시지 마세요. 어지러움이 있으면 운전을 피하세요."
EMERGENCY_BODY = "갑자기 숨이 차거나 가슴 통증이 있으면 즉시 응급실로 가세요."
LIFE_BODY = "가벼운 산책은 괜찮지만 무리한 운동은 피하세요."

SECTIONS = [
    _Section(GuideSectionKey.MEDICATION, MEDICATION_BODY, 1),
    _Section(GuideSectionKey.CAUTION, CAUTION_BODY, 2),
    _Section(GuideSectionKey.EMERGENCY, EMERGENCY_BODY, 3),
    _Section(GuideSectionKey.LIFE, LIFE_BODY, 4),
]


class TestRepresentativeQuestionsFindTheirSection:
    """인수조건 — 복약·주의·생활·응급 각 1건 이상이 승인 섹션을 찾는다.

    (실제 ANSWERED 기록까지는 모델 호출이 필요해서 통합 테스트
    app/tests/chatbot/test_chatbot.py 쪽에서 확인한다 — 여기서는 그
    전 단계인 "섹션을 찾아서 모델을 부르기는 하는가"만 순수 함수로 잰다.
    섹션을 못 찾으면 모델을 부르지도 않고 FALLBACK이 되므로, 이 통과가
    ANSWERED로 가는 필요조건이다.)
    """

    def test_medication_question_finds_the_medication_section(self) -> None:
        context = select_approved_context("약은 왜 먹어야 하나요?", SECTIONS)  # type: ignore[arg-type]
        assert context is not None
        assert context.key is GuideSectionKey.MEDICATION

    def test_caution_question_finds_the_caution_section(self) -> None:
        """원인 ② — 「주의사항이 뭐죠?」가 예전엔 OTHER로 빠져 섹션을 못 찾았다."""
        context = select_approved_context("주의사항이 뭐죠?", SECTIONS)  # type: ignore[arg-type]
        assert context is not None
        assert context.key is GuideSectionKey.CAUTION

    def test_lifestyle_question_finds_the_life_section(self) -> None:
        context = select_approved_context("운동해도 되나요?", SECTIONS)  # type: ignore[arg-type]
        assert context is not None
        assert context.key is GuideSectionKey.LIFE

    def test_emergency_question_finds_the_emergency_section(self) -> None:
        context = select_approved_context("숨이 차고 가슴이 아픈데 어떻게 해야 하나요?", SECTIONS)  # type: ignore[arg-type]
        assert context is not None
        assert context.key is GuideSectionKey.EMERGENCY

    def test_caution_question_does_not_get_outranked_by_emergency(self) -> None:
        """원인 ②를 고치면서 새로 만들 뻔한 버그 — SYMPTOM의 기본 선호 순서가
        (EMERGENCY, CAUTION)이라, '주의'를 SYMPTOM에만 넣으면 응급 신호가
        없어도 EMERGENCY가 이겨 버린다. 명시적 CAUTION 오버라이드로 고쳤다.
        """
        context = select_approved_context("주의사항이 뭐죠?", SECTIONS)  # type: ignore[arg-type]
        assert context is not None
        assert context.key is not GuideSectionKey.EMERGENCY

    def test_an_actual_emergency_signal_still_wins_over_a_caution_word(self) -> None:
        """안전 우선순위 — '주의'와 응급 신호가 같이 있으면 응급이 이겨야 한다."""
        context = select_approved_context("가슴이 아픈데 주의할 게 있나요?", SECTIONS)  # type: ignore[arg-type]
        assert context is not None
        assert context.key is GuideSectionKey.EMERGENCY

    def test_caution_word_classifies_as_symptom(self) -> None:
        assert classify_question("주의사항이 뭐죠?") is PatientQuestionKind.SYMPTOM


class TestGroundingAllowsReorderedVerbatimSentences:
    """원인 ① — 모델이 원문 문장을 그대로 쓰고 순서만 바꾸거나 하나만
    골라도 더 이상 안 막힌다."""

    def test_reordered_sentences_pass(self) -> None:
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)
        answer = "술과 함께 복용하지 마세요. 이 약은 하루 세 번, 식후 30분에 복용하세요."

        assert _is_extractively_grounded(answer, context) is True

    def test_a_single_verbatim_sentence_passes(self) -> None:
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)

        assert _is_extractively_grounded("이 약은 하루 세 번, 식후 30분에 복용하세요.", context) is True

    def test_whitespace_only_differences_do_not_block(self) -> None:
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)
        answer = "이 약은   하루 세 번,\n식후 30분에 복용하세요."

        assert _is_extractively_grounded(answer, context) is True


class TestGroundingStillBlocksAnythingNotVerbatim:
    """안전 회귀 — 승인 안내 밖의 새 문장·진단·복약 중단/변경 권고는
    문장 단위 판정으로 바뀐 뒤에도 여전히 막힌다."""

    def test_a_fabricated_diagnosis_is_blocked(self) -> None:
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)
        answer = "증상을 보니 위염일 가능성이 높습니다. 제산제를 추가로 복용하세요."

        assert _is_extractively_grounded(answer, context) is False

    def test_a_medication_change_recommendation_mixed_with_real_text_is_blocked(self) -> None:
        """원문 문장 하나 + 창작 문장 하나 — 부분적으로만 그대로여도 통째로 막는다."""
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)
        answer = "이 약은 하루 세 번, 식후 30분에 복용하세요. 오늘부터 복용량을 두 배로 늘리세요."

        assert _is_extractively_grounded(answer, context) is False

    def test_a_paraphrased_sentence_is_still_blocked(self) -> None:
        """어미·표현을 다듬은 것도 "그대로 복사"가 아니므로 막는다 —
        문장 단위 판정이 "표현은 자유, 뜻만 맞으면 통과"가 아니라는 것을
        분명히 한다."""
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)
        answer = "이 약은 하루에 세 번 정도, 식사 후 삼십 분 뒤에 드시면 됩니다."

        assert _is_extractively_grounded(answer, context) is False

    def test_an_unrelated_answer_is_blocked(self) -> None:
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)

        assert _is_extractively_grounded("오늘 날씨가 좋네요.", context) is False

    def test_an_empty_answer_is_blocked(self) -> None:
        context = ApprovedContext(key=GuideSectionKey.MEDICATION, body=MEDICATION_BODY)

        assert _is_extractively_grounded("", context) is False
        assert _is_extractively_grounded("   ", context) is False
