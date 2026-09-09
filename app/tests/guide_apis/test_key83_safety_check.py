"""생성 전·후 안전검증 공통 인터페이스 단위 테스트 — KEY-83.

순수 검증 인터페이스를 직접 호출한다.
현재 고정 템플릿 generate() 흐름에 억지로 실패 상태를 만들지 않는다.
"""

from app.services.knowledge_search import ContextAdmissionOutcome
from app.services.safety_check import (
    SafetyReasonCode,
    SafetyVerdictKind,
    post_generate_check,
    pre_generate_check,
)

_SAFE_TEMPLATE = (
    "처방된 약의 용량과 용법은 다음과 같습니다. 담당 의사의 지시를 따라 주세요. 궁금한 점은 병원에 문의해 주세요."
)


class TestPostGenerateCheck:
    def test_normal_fixed_template_passes(self) -> None:
        result = post_generate_check(_SAFE_TEMPLATE)
        assert result.verdict is SafetyVerdictKind.PASS
        assert result.reason_code is None

    def test_extra_drug_blocks(self) -> None:
        result = post_generate_check("처방 외 오메가3를 함께 복용하시면 좋습니다.")
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.EXTRA_DRUG

    def test_extra_drug_blocks_variant(self) -> None:
        result = post_generate_check("처방에 없는 약물을 임의로 추가하지 마세요.")
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.EXTRA_DRUG

    def test_unsupported_diagnosis_blocks(self) -> None:
        result = post_generate_check("당뇨 진단입니다. 처방을 따르세요.")
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.UNSUPPORTED_DIAGNOSIS

    def test_unsupported_diagnosis_blocks_variant(self) -> None:
        result = post_generate_check("다낭성난소증후군으로 진단받으셨습니다.")
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.UNSUPPORTED_DIAGNOSIS

    def test_drug_change_advice_blocks_stop(self) -> None:
        result = post_generate_check("메트포르민은 중단하세요.")
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.DRUG_CHANGE_ADVICE

    def test_drug_change_advice_blocks_dosage(self) -> None:
        result = post_generate_check("복용량을 임의로 증량하지 마십시오.")
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.DRUG_CHANGE_ADVICE

    def test_deterministic_pass(self) -> None:
        r1 = post_generate_check(_SAFE_TEMPLATE)
        r2 = post_generate_check(_SAFE_TEMPLATE)
        assert r1 == r2

    def test_deterministic_block(self) -> None:
        text = "처방 외 약물을 복용하세요."
        r1 = post_generate_check(text)
        r2 = post_generate_check(text)
        assert r1 == r2

    def test_extra_drug_takes_priority_over_drug_change(self) -> None:
        # 처방 외 + 중단 동시 — EXTRA_DRUG가 먼저 잡힌다
        result = post_generate_check("처방 외 약물을 중단하세요.")
        assert result.reason_code is SafetyReasonCode.EXTRA_DRUG

    def test_checker_version_present(self) -> None:
        result = post_generate_check(_SAFE_TEMPLATE)
        assert result.checker_version


class TestPreGenerateCheck:
    def test_search_context_passes(self) -> None:
        result = pre_generate_check(ContextAdmissionOutcome.SEARCH_CONTEXT)
        assert result.verdict is SafetyVerdictKind.PASS
        assert result.reason_code is None

    def test_approved_template_fallback_passes(self) -> None:
        result = pre_generate_check(ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK)
        assert result.verdict is SafetyVerdictKind.PASS

    def test_none_context_blocks(self) -> None:
        result = pre_generate_check(None)
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.UNVERIFIED_CONTEXT

    def test_generation_blocked_blocks(self) -> None:
        result = pre_generate_check(ContextAdmissionOutcome.GENERATION_BLOCKED)
        assert result.verdict is SafetyVerdictKind.BLOCK
        assert result.reason_code is SafetyReasonCode.UNVERIFIED_CONTEXT

    def test_deterministic(self) -> None:
        r1 = pre_generate_check(None)
        r2 = pre_generate_check(None)
        assert r1 == r2

    def test_checker_version_present(self) -> None:
        result = pre_generate_check(ContextAdmissionOutcome.SEARCH_CONTEXT)
        assert result.checker_version
