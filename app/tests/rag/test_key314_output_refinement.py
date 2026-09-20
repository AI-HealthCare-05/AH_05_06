"""KEY-314 patient-facing RAG output contract and immutable fallback."""

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.models.catalog import ApprovalStatus
from app.services.approved_knowledge_search import ApprovedKnowledgeOutcome, ApprovedKnowledgeResult
from app.services.chatbot import ModelAnswer
from app.services.guide_generation import (
    GUIDE_OUTPUT_CONTRACTS,
    GuideGenerationError,
    RagGuideGenerator,
    _output_instructions,
)
from app.services.guide_knowledge_context import GuideSourceValidation
from app.services.knowledge_search import ApprovedFallbackTemplate, fallback_body_checksum


@pytest.mark.parametrize(
    "section_key,title,purpose",
    [
        ("medication", "[복약지도]", "약을 복용하는 이유"),
        ("caution", "[주의사항]", "흔한 반응"),
        ("life", "[생활관리]", "일상 관리"),
    ],
)
def test_section_prompt_has_one_shared_patient_facing_contract(section_key: str, title: str, purpose: str) -> None:
    instructions = _output_instructions(section_key)
    assert title in instructions
    assert purpose in instructions
    assert "일관된 존댓말" in instructions
    assert "겁을 주거나 단정하는 표현을 피하고" in instructions
    assert "한 문장은 짧게" in instructions
    assert "반복하지 말고" in instructions
    assert "본문에 넣지 마세요" in instructions


def test_generated_body_enforces_length_item_and_duplicate_limits() -> None:
    check = RagGuideGenerator._check_answer
    valid = json.dumps({"body": "[생활관리]\n- 규칙적으로 몸을 움직여 주세요.", "drug_names": []})
    body, _ = check(valid, (), section_key="life")
    assert body.startswith("[생활관리]")

    too_long = json.dumps({"body": "가" * (GUIDE_OUTPUT_CONTRACTS["life"].max_chars + 1), "drug_names": []})
    too_many = json.dumps({"body": "\n".join(f"- 서로 다른 안내 문장 {i}입니다." for i in range(7)), "drug_names": []})
    duplicate = json.dumps(
        {"body": "- 매일 가볍게 몸을 움직여 주세요.\n- 매일 가볍게 몸을 움직여 주세요.", "drug_names": []}
    )
    for answer in (too_long, too_many, duplicate):
        with pytest.raises(GuideGenerationError, match="llm_invalid_response"):
            check(answer, (), section_key="life")


async def test_approved_fallback_is_not_rewritten_or_reformatted() -> None:
    body = "승인된 문구는 모양이 달라도 그대로 보존합니다.\n승인된 문구는 모양이 달라도 그대로 보존합니다."
    fallback = ApprovedFallbackTemplate(
        template_id="key314-fixed",
        version="v1",
        body=body,
        body_sha256=fallback_body_checksum(body),
        approval_status=ApprovalStatus.APPROVED,
        is_current=True,
        approved_by="합성 검토자",
        approved_at=date(2026, 9, 18),
    )
    search = AsyncMock()
    search.search.return_value = ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT)
    model = AsyncMock()
    model.generate.return_value = ModelAnswer('{"body":"모델이 바꾼 문구","drug_names":[]}')

    artifact = await RagGuideGenerator(search, model).section(
        hospital_id=1,
        section_key="life",
        query="비식별 합성 질의",
        prescribed_drugs=(),
        fallback=fallback,
    )

    assert artifact.body == body
    assert artifact.validation == GuideSourceValidation()
    model.generate.assert_not_awaited()
