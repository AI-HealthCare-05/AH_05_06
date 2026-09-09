"""안내 생성 전·후 공통 안전검증 계약 — KEY-83.

KEY-277(RAG 생성 연결) 전에 검증 인터페이스와 감사 계약을 선언한다.
현재 고정 템플릿 경로에서는 차단 게이트로 연결하지 않는다.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.knowledge_search import ContextAdmissionOutcome

CHECKER_VERSION = "1.0.0"

# chatbot.py의 _UNSAFE_OUTPUT과 동일한 계약을 공통화. chatbot.py는 여기서 가져간다.
UNSAFE_OUTPUT_PATTERN = re.compile(
    r"(?:진단(?:입니다|으로|받)|(?:약|복용|처방).{0,16}(?:중단|끊으|증량|감량|변경|바꾸|추가)|"
    r"(?:중단|끊으|증량|감량).{0,16}(?:하세요|하십시오|해도))",
    re.IGNORECASE,
)

_EXTRA_DRUG = re.compile(r"처방.{0,10}(?:외|이외|에\s*없)", re.IGNORECASE)
_UNSUPPORTED_DIAGNOSIS = re.compile(r"진단(?:입니다|으로|받)", re.IGNORECASE)
_DRUG_CHANGE_ADVICE = re.compile(
    r"(?:약|복용|처방).{0,16}(?:중단|끊으|증량|감량|변경|바꾸|추가)|"
    r"(?:중단|끊으|증량|감량).{0,16}(?:하세요|하십시오|해도)",
    re.IGNORECASE,
)


class SafetyReasonCode(StrEnum):
    EXTRA_DRUG = "EXTRA_DRUG"
    UNSUPPORTED_DIAGNOSIS = "UNSUPPORTED_DIAGNOSIS"
    DRUG_CHANGE_ADVICE = "DRUG_CHANGE_ADVICE"
    UNVERIFIED_CONTEXT = "UNVERIFIED_CONTEXT"


class SafetyVerdictKind(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SafetyVerdict:
    verdict: SafetyVerdictKind
    reason_code: SafetyReasonCode | None = None
    checker_version: str = field(default=CHECKER_VERSION)


_PASS = SafetyVerdict(verdict=SafetyVerdictKind.PASS)


def pre_generate_check(context_outcome: ContextAdmissionOutcome | None) -> SafetyVerdict:
    """생성 컨텍스트의 안전 여부를 판정한다.

    검증되지 않은 컨텍스트(None 또는 GENERATION_BLOCKED)는 BLOCK.
    실제 차단 게이트 연결은 KEY-277에서 수행한다.
    """
    if context_outcome is None or context_outcome is ContextAdmissionOutcome.GENERATION_BLOCKED:
        return SafetyVerdict(
            verdict=SafetyVerdictKind.BLOCK,
            reason_code=SafetyReasonCode.UNVERIFIED_CONTEXT,
        )
    return _PASS


def post_generate_check(output_text: str) -> SafetyVerdict:
    """생성된 텍스트의 안전 여부를 판정한다.

    EXTRA_DRUG → UNSUPPORTED_DIAGNOSIS → DRUG_CHANGE_ADVICE 순으로 검사하며
    첫 번째 매칭에서 반환한다. 실제 차단 게이트 연결은 KEY-277에서 수행한다.
    """
    if _EXTRA_DRUG.search(output_text):
        return SafetyVerdict(
            verdict=SafetyVerdictKind.BLOCK,
            reason_code=SafetyReasonCode.EXTRA_DRUG,
        )
    if _UNSUPPORTED_DIAGNOSIS.search(output_text):
        return SafetyVerdict(
            verdict=SafetyVerdictKind.BLOCK,
            reason_code=SafetyReasonCode.UNSUPPORTED_DIAGNOSIS,
        )
    if _DRUG_CHANGE_ADVICE.search(output_text):
        return SafetyVerdict(
            verdict=SafetyVerdictKind.BLOCK,
            reason_code=SafetyReasonCode.DRUG_CHANGE_ADVICE,
        )
    return _PASS
