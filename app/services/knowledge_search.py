"""승인 의료지식 검색의 작은 안전 경계와 코사인 PoC — KEY-82.

이 모듈은 RAG 생성기가 아니다. MySQL 8에서 읽은 후보를 다시 검증하고,
Python에서 코사인 유사도로 정렬하는 최소 검색 계약만 담는다. 검색 결과는
안내문 초안의 근거 후보일 뿐이며 환자에게 직접 노출하거나 자동 승인하지 않는다.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from math import isfinite, sqrt

from app.models.catalog import ApprovalStatus, SourceGrade

DEFAULT_TOP_K = 3
DEFAULT_MIN_SIMILARITY = 0.72
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
EMBEDDING_DIMENSION = 384


class KnowledgeSearchOutcome(StrEnum):
    FOUND = "found"
    NO_EVIDENCE = "no_evidence"
    SOURCE_CONFLICT = "source_conflict"
    INDEX_INVALID = "index_invalid"


class ContextAdmissionOutcome(StrEnum):
    SEARCH_CONTEXT = "search_context"
    APPROVED_TEMPLATE_FALLBACK = "approved_template_fallback"
    GENERATION_BLOCKED = "generation_blocked"


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    hospital_id: int | None
    section_key: str
    body: str
    embedding: tuple[float, ...]
    approval_status: ApprovalStatus
    is_current: bool
    source_grade: SourceGrade
    license_verified: bool
    verified_at: date
    review_due_at: date | None
    claim_key: str | None = None
    claim_value: str | None = None


@dataclass(frozen=True)
class KnowledgeSearchScope:
    hospital_id: int
    allowed_sections: frozenset[str]
    searched_at: date


@dataclass(frozen=True)
class KnowledgeSearchHit:
    chunk: KnowledgeChunk
    score: float


@dataclass(frozen=True)
class KnowledgeSearchResult:
    outcome: KnowledgeSearchOutcome
    hits: tuple[KnowledgeSearchHit, ...] = ()


@dataclass(frozen=True)
class ApprovedFallbackTemplate:
    template_id: str
    version: str
    body: str
    body_sha256: str
    approval_status: ApprovalStatus
    is_current: bool
    approved_by: str
    approved_at: date


@dataclass(frozen=True)
class PocEvaluationApproval:
    evaluation_id: str
    passed: bool
    approved_by: str
    approved_at: date
    result_sha256: str


@dataclass(frozen=True)
class GenerationContextAdmission:
    outcome: ContextAdmissionOutcome
    hits: tuple[KnowledgeSearchHit, ...] = ()
    fallback_template: ApprovedFallbackTemplate | None = None


def fallback_body_checksum(body: str) -> str:
    """승인 당시 고정한 fallback 본문의 SHA-256을 반환한다."""

    return sha256(body.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """같은 차원의 0이 아닌 두 벡터의 코사인 유사도를 계산한다."""

    if not left or len(left) != len(right):
        raise ValueError("embedding dimensions must be equal and non-empty")
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embedding vectors must be non-zero")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _is_valid_embedding(embedding: tuple[float, ...]) -> bool:
    return (
        len(embedding) == EMBEDDING_DIMENSION
        and all(isfinite(value) for value in embedding)
        and any(value != 0 for value in embedding)
    )


def _eligible(chunk: KnowledgeChunk, scope: KnowledgeSearchScope) -> bool:
    return (
        chunk.approval_status is ApprovalStatus.APPROVED
        and chunk.is_current
        and chunk.source_grade is SourceGrade.A
        and chunk.license_verified
        and (chunk.hospital_id is None or chunk.hospital_id == scope.hospital_id)
        and chunk.section_key in scope.allowed_sections
        and (chunk.review_due_at is None or chunk.review_due_at >= scope.searched_at)
        and bool(chunk.body.strip())
    )


def _has_conflict(hits: list[KnowledgeSearchHit]) -> bool:
    claims: dict[str, set[str]] = {}
    for hit in hits:
        key = hit.chunk.claim_key
        value = hit.chunk.claim_value
        if key and value:
            claims.setdefault(key, set()).add(value)
    return any(len(values) > 1 for values in claims.values())


def search_approved_knowledge(
    query_embedding: tuple[float, ...],
    chunks: list[KnowledgeChunk],
    scope: KnowledgeSearchScope,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> KnowledgeSearchResult:
    """승인·현재 버전·출처·병원 경계를 통과한 청크만 검색한다.

    질의 또는 검색 대상 청크의 임베딩 차원이 현재 계약(384)과 다르거나 0 벡터면
    그 청크만 무시하지 않고 전체 검색을 차단한다. 부분 재색인 중 오래된 벡터를
    조용히 섞는 것보다 안전하게 실패하는 편이 낫다. 출처 충돌은 실제 반환되는
    ``top_k``뿐 아니라 최소 유사도를 넘은 전체 후보에서 검사한다.
    """

    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not 0 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between 0 and 1")
    if not _is_valid_embedding(query_embedding):
        return KnowledgeSearchResult(KnowledgeSearchOutcome.INDEX_INVALID)

    ranked: list[KnowledgeSearchHit] = []
    for chunk in chunks:
        if not _eligible(chunk, scope):
            continue
        if not _is_valid_embedding(chunk.embedding):
            return KnowledgeSearchResult(KnowledgeSearchOutcome.INDEX_INVALID)
        score = cosine_similarity(query_embedding, chunk.embedding)
        if score >= min_similarity:
            ranked.append(KnowledgeSearchHit(chunk=chunk, score=score))

    ranked.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
    if not ranked:
        return KnowledgeSearchResult(KnowledgeSearchOutcome.NO_EVIDENCE)
    if _has_conflict(ranked):
        return KnowledgeSearchResult(KnowledgeSearchOutcome.SOURCE_CONFLICT)
    return KnowledgeSearchResult(KnowledgeSearchOutcome.FOUND, tuple(ranked[:top_k]))


def admit_generation_context(
    search_result: KnowledgeSearchResult,
    *,
    evaluation_approval: PocEvaluationApproval | None,
    fallback_template: ApprovedFallbackTemplate | None = None,
) -> GenerationContextAdmission:
    """검증된 검색 결과를 생성 컨텍스트 또는 승인 fallback으로 들이는 진입 관문.

    ``search_result``는 동일 요청의 병원·섹션·검색일 범위로
    :func:`search_approved_knowledge`가 반환한 결과여야 한다. 이 함수에는 해당 범위가
    없으므로 hit의 승인·병원 경계를 다시 판정하지 않는다. PoC 평가가 통과하기
    전에는 검색 성공 여부와 관계없이 생성 연결을 막는다. 통과 후에도 검증이 끝난
    ``FOUND`` 결과만 컨텍스트로 들어간다. 근거가 없는 경우에는 승인된 현재 버전의
    고정 템플릿만 허용하며, 충돌이나 인덱스 오류는 템플릿으로 덮지 않고 차단한다.
    """

    if (
        evaluation_approval is None
        or not evaluation_approval.passed
        or not evaluation_approval.evaluation_id.strip()
        or not evaluation_approval.approved_by.strip()
        or not _is_sha256_hex(evaluation_approval.result_sha256)
    ):
        return GenerationContextAdmission(ContextAdmissionOutcome.GENERATION_BLOCKED)
    if search_result.outcome is KnowledgeSearchOutcome.FOUND and search_result.hits:
        return GenerationContextAdmission(ContextAdmissionOutcome.SEARCH_CONTEXT, hits=search_result.hits)
    if search_result.outcome is not KnowledgeSearchOutcome.NO_EVIDENCE:
        return GenerationContextAdmission(ContextAdmissionOutcome.GENERATION_BLOCKED)
    if (
        fallback_template is None
        or not fallback_template.template_id.strip()
        or not fallback_template.version.strip()
        or fallback_template.approval_status is not ApprovalStatus.APPROVED
        or not fallback_template.is_current
        or not fallback_template.body.strip()
        or not fallback_template.approved_by.strip()
        or fallback_template.body_sha256 != fallback_body_checksum(fallback_template.body)
    ):
        return GenerationContextAdmission(ContextAdmissionOutcome.GENERATION_BLOCKED)
    return GenerationContextAdmission(
        ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK,
        fallback_template=fallback_template,
    )
