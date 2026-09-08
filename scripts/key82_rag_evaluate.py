"""KEY-82 합성 retrieval 평가셋과 생성 컨텍스트 진입 규칙을 재현한다."""

import json
import sys
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.catalog import ApprovalStatus, SourceGrade  # noqa: E402
from app.services.knowledge_search import (  # noqa: E402
    EMBEDDING_DIMENSION,
    ApprovedFallbackTemplate,
    ContextAdmissionOutcome,
    KnowledgeChunk,
    KnowledgeSearchOutcome,
    KnowledgeSearchScope,
    PocEvaluationApproval,
    admit_generation_context,
    fallback_body_checksum,
    search_approved_knowledge,
)

CHUNKS_PATH = ROOT / "docs" / "data" / "key82-rag-poc-chunks.json"
EVALUATION_PATH = ROOT / "docs" / "data" / "key82-rag-poc-evaluation.json"
EVALUATED_AT = date(2026, 9, 7)

PASS_CRITERIA = {
    "outcome_accuracy_min": 1.0,
    "recall_at_3_min": 0.9,
    "precision_at_3_min": 0.9,
    "admission_accuracy_min": 1.0,
    "unsafe_context_entries_max": 0,
}


def _poc_embedding(values: list[float]) -> tuple[float, ...]:
    """3차원 합성값을 운영 검색 계약의 384차원 벡터로 확장한다."""

    embedding = tuple(float(value) for value in values)
    if len(embedding) > EMBEDDING_DIMENSION:
        raise ValueError("PoC embedding exceeds the fixed embedding dimension")
    return embedding + (0.0,) * (EMBEDDING_DIMENSION - len(embedding))


def _chunk(row: dict[str, Any]) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        hospital_id=row["hospital_id"],
        section_key=row["section_key"],
        body=row["body"],
        embedding=_poc_embedding(row["embedding"]),
        approval_status=ApprovalStatus(row["approval_status"]),
        is_current=bool(row["is_current"]),
        source_grade=SourceGrade(row["source_grade"]),
        license_verified=bool(row["license_verified"]),
        verified_at=date.fromisoformat(row["verified_at"]),
        review_due_at=date.fromisoformat(row["review_due_at"]) if row["review_due_at"] else None,
        claim_key=row["claim_key"],
        claim_value=row["claim_value"],
    )


def _fallback_template() -> ApprovedFallbackTemplate:
    body = "[합성 평가] 검증 가능한 근거가 없어 승인된 안내를 표시합니다."
    return ApprovedFallbackTemplate(
        template_id="synthetic-no-evidence-fallback",
        version="1.0.0",
        body=body,
        body_sha256=fallback_body_checksum(body),
        approval_status=ApprovalStatus.APPROVED,
        is_current=True,
        approved_by="synthetic-medical-safety-reviewer",
        approved_at=EVALUATED_AT,
    )


def _synthetic_evaluation_approval() -> PocEvaluationApproval:
    return PocEvaluationApproval(
        evaluation_id="synthetic-key82-evaluation-v1",
        passed=True,
        approved_by="synthetic-designated-reviewer",
        approved_at=EVALUATED_AT,
        result_sha256="a" * 64,
    )


def evaluate(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    chunks = [_chunk(row) for row in json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))]
    if cases is None:
        cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    if not cases:
        raise ValueError("evaluation cases must not be empty")
    outcome_correct = 0
    admission_correct = 0
    expected_hits = 0
    relevant_hits = 0
    retrieved_hits = 0
    unsafe_context_entries = 0
    failures: list[str] = []

    for case in cases:
        result = search_approved_knowledge(
            _poc_embedding(case["query_embedding"]),
            chunks,
            KnowledgeSearchScope(
                hospital_id=case["hospital_id"],
                allowed_sections=frozenset(case["allowed_sections"]),
                searched_at=EVALUATED_AT,
            ),
        )
        admission = admit_generation_context(
            result,
            evaluation_approval=_synthetic_evaluation_approval(),
            fallback_template=_fallback_template(),
        )
        actual_ids = {hit.chunk.chunk_id for hit in result.hits}
        expected_ids = set(case["expected_hit_ids"])
        forbidden_ids = set(case["forbidden_hit_ids"])

        outcome_matches = result.outcome is KnowledgeSearchOutcome(case["expected_outcome"])
        admission_matches = admission.outcome is ContextAdmissionOutcome(case["expected_admission"])
        outcome_correct += int(outcome_matches)
        admission_correct += int(admission_matches)
        expected_hits += len(expected_ids)
        relevant_hits += len(actual_ids & expected_ids)
        retrieved_hits += len(actual_ids)
        unsafe_context_entries += len(actual_ids & forbidden_ids)

        if not outcome_matches or not admission_matches or actual_ids != expected_ids:
            failures.append(case["query_id"])

    recall_at_3 = relevant_hits / expected_hits if expected_hits else None
    precision_at_3 = relevant_hits / retrieved_hits if retrieved_hits else None
    if recall_at_3 is None:
        failures.append("evaluation-set:no-positive-expected-hits")
    if precision_at_3 is None:
        failures.append("evaluation-set:no-retrieved-hits")

    outcome_accuracy = outcome_correct / len(cases)
    admission_accuracy = admission_correct / len(cases)
    metrics = {
        "outcome_accuracy": outcome_accuracy,
        "recall_at_3": recall_at_3,
        "precision_at_3": precision_at_3,
        "admission_accuracy": admission_accuracy,
        "unsafe_context_entries": unsafe_context_entries,
    }
    passed = (
        outcome_accuracy >= PASS_CRITERIA["outcome_accuracy_min"]
        and recall_at_3 is not None
        and recall_at_3 >= PASS_CRITERIA["recall_at_3_min"]
        and precision_at_3 is not None
        and precision_at_3 >= PASS_CRITERIA["precision_at_3_min"]
        and admission_accuracy >= PASS_CRITERIA["admission_accuracy_min"]
        and unsafe_context_entries <= PASS_CRITERIA["unsafe_context_entries_max"]
        and not failures
    )
    report = {
        "evaluated_at": EVALUATED_AT.isoformat(),
        "case_count": len(cases),
        "criteria": PASS_CRITERIA,
        "metrics": metrics,
        "failed_cases": failures,
        "passed": passed,
    }
    report["result_sha256"] = sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report


def main() -> None:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
