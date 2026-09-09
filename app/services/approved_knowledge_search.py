"""DB의 승인 의료지식을 KEY-82 Python cosine 계약으로 검색한다 — KEY-276."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from tortoise.expressions import Q

from app.models.catalog import ApprovalStatus, SourceGrade
from app.models.knowledge import KnowledgeChunkRecord
from app.services.knowledge_pipeline import EmbeddingProvider
from app.services.knowledge_search import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TOP_K,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_MODEL_REVISION,
    KnowledgeChunk,
    KnowledgeSearchOutcome,
    KnowledgeSearchScope,
    search_approved_knowledge,
)


class ApprovedKnowledgeOutcome(StrEnum):
    FOUND = "found"
    NO_VERIFIED_CONTEXT = "no_verified_context"
    SOURCE_CONFLICT = "source_conflict"
    INDEX_INVALID = "index_invalid"


@dataclass(frozen=True)
class ApprovedKnowledgeHit:
    document_id: str
    chunk_id: str
    source_org: str
    source_url: str
    version: str
    verified_at: date
    hospital_id: int | None
    score: float
    validation_status: str = "approved_current"


@dataclass(frozen=True)
class ApprovedKnowledgeResult:
    outcome: ApprovedKnowledgeOutcome
    hits: tuple[ApprovedKnowledgeHit, ...] = ()


class ApprovedKnowledgeSearchService:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._embedding_provider = embedding_provider

    async def search(
        self,
        query: str,
        *,
        hospital_id: int,
        allowed_sections: frozenset[str],
        searched_at: date,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> ApprovedKnowledgeResult:
        if not query.strip():
            return ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT)
        if (
            self._embedding_provider.model != EMBEDDING_MODEL
            or self._embedding_provider.revision != EMBEDDING_MODEL_REVISION
            or self._embedding_provider.dimension != EMBEDDING_DIMENSION
        ):
            return ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.INDEX_INVALID)

        query_vectors = await self._embedding_provider.embed((query,))
        records = (
            await KnowledgeChunkRecord.filter(
                Q(version__document__hospital_id=None) | Q(version__document__hospital_id=hospital_id),
                version__approval_status=ApprovalStatus.APPROVED,
                version__is_current=True,
                version__source_grade=SourceGrade.A,
                version__license_verified=True,
                version__verified_at__not_isnull=True,
                version__document__source_url__not_isnull=True,
                section_key__in=allowed_sections,
                embedding_model=EMBEDDING_MODEL,
                embedding_revision=EMBEDDING_MODEL_REVISION,
                embedding_dimension=EMBEDDING_DIMENSION,
            )
            .prefetch_related("version__document")
            .order_by("chunk_id")
        )

        chunks: list[KnowledgeChunk] = []
        record_by_chunk_id: dict[str, KnowledgeChunkRecord] = {}
        for record in records:
            version = record.version
            document = version.document
            if version.verified_at is None or not document.source_url or not document.source_org:
                continue
            chunk_id = str(record.chunk_id)
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    document_id=str(document.document_id),
                    hospital_id=document.hospital_id,
                    section_key=record.section_key,
                    body=record.body,
                    embedding=tuple(float(value) for value in record.embedding),
                    approval_status=version.approval_status,
                    is_current=version.is_current,
                    source_grade=version.source_grade,
                    license_verified=version.license_verified,
                    verified_at=version.verified_at.date(),
                    review_due_at=version.review_due_at.date() if version.review_due_at else None,
                    claim_key=record.claim_key,
                    claim_value=record.claim_value,
                )
            )
            record_by_chunk_id[chunk_id] = record

        result = search_approved_knowledge(
            query_vectors[0],
            chunks,
            KnowledgeSearchScope(
                hospital_id=hospital_id,
                allowed_sections=allowed_sections,
                searched_at=searched_at,
            ),
            top_k=top_k,
            min_similarity=min_similarity,
        )
        if result.outcome is KnowledgeSearchOutcome.NO_EVIDENCE:
            return ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT)
        if result.outcome is KnowledgeSearchOutcome.SOURCE_CONFLICT:
            return ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.SOURCE_CONFLICT)
        if result.outcome is KnowledgeSearchOutcome.INDEX_INVALID:
            return ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.INDEX_INVALID)

        hits = []
        for hit in result.hits:
            record = record_by_chunk_id[hit.chunk.chunk_id]
            version = record.version
            document = version.document
            hits.append(
                ApprovedKnowledgeHit(
                    document_id=str(document.document_id),
                    chunk_id=str(record.chunk_id),
                    source_org=document.source_org,
                    source_url=document.source_url or "",
                    version=version.version_label,
                    verified_at=version.verified_at.date(),  # type: ignore[union-attr]
                    hospital_id=document.hospital_id,
                    score=hit.score,
                )
            )
        return ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.FOUND, tuple(hits))
