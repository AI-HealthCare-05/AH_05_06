from dataclasses import replace
from datetime import date
from typing import Any, cast

import pytest

from app.models.catalog import ApprovalStatus, SourceGrade
from app.services.knowledge_search import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TOP_K,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_MODEL_REVISION,
    ApprovedFallbackTemplate,
    ContextAdmissionOutcome,
    KnowledgeChunk,
    KnowledgeSearchHit,
    KnowledgeSearchOutcome,
    KnowledgeSearchResult,
    KnowledgeSearchScope,
    PocEvaluationApproval,
    admit_generation_context,
    cosine_similarity,
    fallback_body_checksum,
    search_approved_knowledge,
)
from scripts.key82_rag_evaluate import evaluate
from scripts.key82_rag_poc import _poc_passed

TODAY = date(2026, 9, 7)
SCOPE = KnowledgeSearchScope(
    hospital_id=1,
    allowed_sections=frozenset({"medication", "caution", "emergency", "life"}),
    searched_at=TODAY,
)


def embedding(*values: float) -> tuple[float, ...]:
    if len(values) > EMBEDDING_DIMENSION:
        raise ValueError("test embedding exceeds the fixed dimension")
    return values + (0.0,) * (EMBEDDING_DIMENSION - len(values))


def chunk(chunk_id: str, vector: tuple[float, ...] | None = None, **changes: object) -> KnowledgeChunk:
    base = KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=f"document-{chunk_id}",
        hospital_id=None,
        section_key="medication",
        body=f"[합성] {chunk_id}",
        embedding=vector if vector is not None else embedding(1.0, 0.0, 0.0),
        approval_status=ApprovalStatus.APPROVED,
        is_current=True,
        source_grade=SourceGrade.A,
        license_verified=True,
        verified_at=TODAY,
        review_due_at=date(2099, 12, 31),
    )
    return replace(base, **cast(dict[str, Any], changes))


def test_fixed_retrieval_parameters() -> None:
    assert DEFAULT_TOP_K == 3
    assert DEFAULT_MIN_SIMILARITY == 0.72
    assert EMBEDDING_MODEL == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert EMBEDDING_MODEL_REVISION == "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    assert EMBEDDING_DIMENSION == 384


def test_cosine_similarity() -> None:
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)


def test_only_current_approved_a_grade_licensed_fresh_and_scoped_chunks_are_returned() -> None:
    allowed = chunk("allowed")
    candidates = [
        allowed,
        chunk("draft", approval_status=ApprovalStatus.DRAFT),
        chunk("deprecated", approval_status=ApprovalStatus.DEPRECATED),
        chunk("old-version", is_current=False),
        chunk("b-grade", source_grade=SourceGrade.B),
        chunk("c-grade", source_grade=SourceGrade.C),
        chunk("unlicensed", license_verified=False),
        chunk("stale", review_due_at=date(2026, 9, 6)),
        chunk("other-hospital", hospital_id=2),
        chunk("wrong-section", section_key="messages"),
    ]

    result = search_approved_knowledge(embedding(1.0, 0.0, 0.0), candidates, SCOPE)

    assert result.outcome is KnowledgeSearchOutcome.FOUND
    assert [hit.chunk.chunk_id for hit in result.hits] == [allowed.chunk_id]


def test_below_threshold_returns_no_evidence() -> None:
    result = search_approved_knowledge(embedding(1.0, 0.0, 0.0), [chunk("unrelated", embedding(0.0, 1.0, 0.0))], SCOPE)

    assert result.outcome is KnowledgeSearchOutcome.NO_EVIDENCE
    assert result.hits == ()


def test_conflicting_high_similarity_claims_fail_closed() -> None:
    candidates = [
        chunk("claim-a", claim_key="synthetic-rule", claim_value="A"),
        chunk("claim-b", embedding(0.99, 0.01, 0.0), claim_key="synthetic-rule", claim_value="B"),
    ]

    result = search_approved_knowledge(embedding(1.0, 0.0, 0.0), candidates, SCOPE)

    assert result.outcome is KnowledgeSearchOutcome.SOURCE_CONFLICT
    assert result.hits == ()


def test_embedding_dimension_drift_fails_closed() -> None:
    result = search_approved_knowledge(embedding(1.0, 0.0, 0.0), [chunk("old-index", (1.0, 0.0))], SCOPE)

    assert result.outcome is KnowledgeSearchOutcome.INDEX_INVALID
    assert result.hits == ()


def test_top_k_is_deterministic() -> None:
    candidates = [chunk("c"), chunk("a"), chunk("d"), chunk("b")]

    result = search_approved_knowledge(embedding(1.0, 0.0, 0.0), candidates, SCOPE)

    assert result.outcome is KnowledgeSearchOutcome.FOUND
    assert [hit.chunk.chunk_id for hit in result.hits] == ["a", "b", "c"]


def approved_fallback(**changes: object) -> ApprovedFallbackTemplate:
    body = "[합성] 근거를 찾지 못해 의료진 검토가 필요합니다."
    template = ApprovedFallbackTemplate(
        template_id="synthetic-approved-fallback-v1",
        version="1.0.0",
        body=body,
        body_sha256=fallback_body_checksum(body),
        approval_status=ApprovalStatus.APPROVED,
        is_current=True,
        approved_by="synthetic-medical-safety-reviewer",
        approved_at=TODAY,
    )
    return replace(template, **cast(dict[str, Any], changes))


def evaluation_approval(**changes: object) -> PocEvaluationApproval:
    approval = PocEvaluationApproval(
        evaluation_id="synthetic-key82-evaluation-v1",
        passed=True,
        approved_by="synthetic-designated-reviewer",
        approved_at=TODAY,
        result_sha256="a" * 64,
    )
    return replace(approval, **cast(dict[str, Any], changes))


def test_generation_is_blocked_before_poc_evaluation_passes() -> None:
    found = search_approved_knowledge(embedding(1.0, 0.0, 0.0), [chunk("allowed")], SCOPE)

    admission = admit_generation_context(found, evaluation_approval=None)

    assert admission.outcome is ContextAdmissionOutcome.GENERATION_BLOCKED
    assert admission.hits == ()


def test_only_validated_found_result_enters_generation_context() -> None:
    found = search_approved_knowledge(embedding(1.0, 0.0, 0.0), [chunk("allowed")], SCOPE)

    admission = admit_generation_context(found, evaluation_approval=evaluation_approval())

    assert admission.outcome is ContextAdmissionOutcome.SEARCH_CONTEXT
    assert [hit.chunk.chunk_id for hit in admission.hits] == ["allowed"]
    assert admission.fallback_template is None


def test_no_evidence_uses_only_current_approved_fallback_template() -> None:
    no_evidence = search_approved_knowledge(embedding(1.0, 0.0, 0.0), [], SCOPE)

    admitted = admit_generation_context(
        no_evidence,
        evaluation_approval=evaluation_approval(),
        fallback_template=approved_fallback(),
    )
    draft_blocked = admit_generation_context(
        no_evidence,
        evaluation_approval=evaluation_approval(),
        fallback_template=approved_fallback(approval_status=ApprovalStatus.DRAFT),
    )

    assert admitted.outcome is ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK
    assert admitted.hits == ()
    assert admitted.fallback_template == approved_fallback()
    assert draft_blocked.outcome is ContextAdmissionOutcome.GENERATION_BLOCKED


def test_fallback_with_changed_body_or_missing_approval_record_is_blocked() -> None:
    no_evidence = KnowledgeSearchResult(KnowledgeSearchOutcome.NO_EVIDENCE)

    changed_body = admit_generation_context(
        no_evidence,
        evaluation_approval=evaluation_approval(),
        fallback_template=approved_fallback(body="승인 뒤 바뀐 본문"),
    )
    missing_reviewer = admit_generation_context(
        no_evidence,
        evaluation_approval=evaluation_approval(),
        fallback_template=approved_fallback(approved_by=""),
    )

    assert changed_body.outcome is ContextAdmissionOutcome.GENERATION_BLOCKED
    assert missing_reviewer.outcome is ContextAdmissionOutcome.GENERATION_BLOCKED


def test_conflict_and_invalid_index_never_fall_back() -> None:
    template = approved_fallback()

    for outcome in (KnowledgeSearchOutcome.SOURCE_CONFLICT, KnowledgeSearchOutcome.INDEX_INVALID):
        admission = admit_generation_context(
            KnowledgeSearchResult(outcome),
            evaluation_approval=evaluation_approval(),
            fallback_template=template,
        )
        assert admission.outcome is ContextAdmissionOutcome.GENERATION_BLOCKED
        assert admission.fallback_template is None


def test_failed_or_incomplete_evaluation_approval_does_not_open_generation() -> None:
    found = KnowledgeSearchResult(KnowledgeSearchOutcome.FOUND, (KnowledgeSearchHit(chunk("ok"), 1.0),))

    for approval in (
        evaluation_approval(passed=False),
        evaluation_approval(approved_by=""),
        evaluation_approval(result_sha256="missing"),
        evaluation_approval(result_sha256="x" * 64),
        evaluation_approval(result_sha256="ab" + " " * 62),
    ):
        admission = admit_generation_context(found, evaluation_approval=approval)
        assert admission.outcome is ContextAdmissionOutcome.GENERATION_BLOCKED


def test_synthetic_evaluation_dataset_meets_fixed_gates() -> None:
    result = evaluate()

    assert result["passed"] is True
    assert result["case_count"] == 6
    assert result["metrics"] == {
        "outcome_accuracy": 1.0,
        "recall_at_3": 1.0,
        "precision_at_3": 1.0,
        "admission_accuracy": 1.0,
        "unsafe_context_entries": 0,
    }


def test_negative_only_evaluation_is_reported_as_failed_instead_of_dividing_by_zero() -> None:
    negative_case = {
        "query_id": "negative-only",
        "query_embedding": [-1.0, 0.0, 0.0],
        "hospital_id": 1,
        "allowed_sections": ["medication"],
        "expected_outcome": "no_evidence",
        "expected_hit_ids": [],
        "expected_admission": "approved_template_fallback",
        "forbidden_hit_ids": [],
    }

    result = evaluate([negative_case])

    assert result["passed"] is False
    assert result["metrics"]["recall_at_3"] is None
    assert result["metrics"]["precision_at_3"] is None
    assert "evaluation-set:no-positive-expected-hits" in result["failed_cases"]
    assert "evaluation-set:no-retrieved-hits" in result["failed_cases"]


def test_fixed_embedding_dimension_and_zero_query_fail_closed() -> None:
    assert (
        search_approved_knowledge((1.0, 0.0), [chunk("allowed")], SCOPE).outcome is KnowledgeSearchOutcome.INDEX_INVALID
    )
    assert (
        search_approved_knowledge((0.0,) * EMBEDDING_DIMENSION, [chunk("allowed")], SCOPE).outcome
        is KnowledgeSearchOutcome.INDEX_INVALID
    )
    assert (
        search_approved_knowledge(
            embedding(1.0, 0.0, 0.0),
            [chunk("zero-index", (0.0,) * EMBEDDING_DIMENSION)],
            SCOPE,
        ).outcome
        is KnowledgeSearchOutcome.INDEX_INVALID
    )


def test_missing_review_due_date_uses_current_version_as_primary_time_axis() -> None:
    result = search_approved_knowledge(
        embedding(1.0, 0.0, 0.0),
        [chunk("undated", review_due_at=None)],
        SCOPE,
    )

    assert result.outcome is KnowledgeSearchOutcome.FOUND


def test_mysql_poc_passes_only_for_the_expected_found_result() -> None:
    expected = KnowledgeSearchResult(
        KnowledgeSearchOutcome.FOUND,
        (KnowledgeSearchHit(chunk("synthetic-medication-current"), 1.0),),
    )

    assert _poc_passed(expected) is True
    assert _poc_passed(KnowledgeSearchResult(KnowledgeSearchOutcome.NO_EVIDENCE)) is False
    assert _poc_passed(KnowledgeSearchResult(KnowledgeSearchOutcome.INDEX_INVALID)) is False


def test_conflict_above_threshold_blocks_even_when_outside_top_k() -> None:
    candidates = [
        chunk("a"),
        chunk("b"),
        chunk("c"),
        chunk("d", claim_key="synthetic-rule", claim_value="A"),
        chunk("e", claim_key="synthetic-rule", claim_value="B"),
    ]

    result = search_approved_knowledge(embedding(1.0, 0.0, 0.0), candidates, SCOPE, top_k=3)

    assert result.outcome is KnowledgeSearchOutcome.SOURCE_CONFLICT
