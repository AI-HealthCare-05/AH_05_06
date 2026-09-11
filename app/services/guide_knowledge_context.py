"""KEY-277 연결 준비: 검색 후 현재 DB를 재검증한 근거 스냅샷.

LLM 호출·GuideService 배선은 하지 않는다. 기존 KEY-75 상태기계를 재사용하는 운영 연결에서 호출자가 이 결과를 섹션별로 저장하고 사용하는 계약이다.
"""

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from math import isfinite
from uuid import UUID

from app.models.catalog import ApprovalStatus, SourceGrade
from app.models.knowledge import KnowledgeChunkRecord
from app.services.approved_knowledge_search import ApprovedKnowledgeOutcome, ApprovedKnowledgeResult
from app.services.knowledge_search import DEFAULT_MIN_SIMILARITY


@dataclass(frozen=True)
class VerifiedGuideSource:
    document_id: str
    chunk_id: str
    section_key: str
    source_org: str
    source_url: str
    version: str
    verified_at: date
    hospital_id: int | None
    score: float
    body_sha256: str
    body: str = field(repr=False)


@dataclass(frozen=True)
class GuideSourceValidation:
    sources: tuple[VerifiedGuideSource, ...] = ()
    block_reason: str | None = None


async def revalidate_guide_sources(
    result: ApprovedKnowledgeResult,
    *,
    hospital_id: int,
    section_key: str,
    checked_at: date,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> GuideSourceValidation:
    """하나라도 불일치하면 전체를 차단해 부분 근거로 생성하지 않는다."""
    if result.outcome is not ApprovedKnowledgeOutcome.FOUND:
        return GuideSourceValidation(block_reason=result.outcome.value)
    if not result.hits:
        return GuideSourceValidation(block_reason="empty_found_hits")
    if not isfinite(min_similarity) or not 0 <= min_similarity <= 1:
        return GuideSourceValidation(block_reason="invalid_min_similarity")
    try:
        ids = [UUID(hit.chunk_id) for hit in result.hits]
    except (ValueError, TypeError, AttributeError):
        return GuideSourceValidation(block_reason="invalid_chunk_id")
    if len(set(ids)) != len(ids):
        return GuideSourceValidation(block_reason="duplicate_chunk_id")
    records = await KnowledgeChunkRecord.filter(chunk_id__in=ids).prefetch_related("version__document")
    by_id = {str(record.chunk_id): record for record in records}
    snapshots = []
    for hit in result.hits:
        record = by_id.get(hit.chunk_id)
        if record is None:
            return GuideSourceValidation(block_reason="missing_chunk")
        version = record.version
        document = version.document
        verified = version.verified_at.date() if version.verified_at else None
        checks = (
            (version.approval_status is not ApprovalStatus.APPROVED, "approval_status"),
            (not version.is_current, "is_current"),
            (version.current_approved_key != str(document.document_id), "current_approved_key"),
            (version.source_grade is not SourceGrade.A, "source_grade"),
            (not version.license_verified, "license_verified"),
            (not version.approved_by, "approved_by"),
            (version.approved_at is None, "approved_at"),
            (version.approved_at is not None and version.approved_at.date() > checked_at, "approved_at_future"),
            (verified is None, "verified_at"),
            (verified is not None and verified > checked_at, "verified_at_future"),
            ((version.review_due_at is not None and version.review_due_at.date() < checked_at), "review_due_at"),
            (document.hospital_id not in (None, hospital_id), "hospital_scope"),
            (record.section_key != section_key, "section_key"),
            (not document.source_org.strip(), "source_org"),
            (not document.source_url, "source_url"),
            (document.source_url is not None and not document.source_url.strip(), "source_url_blank"),
            (not record.body.strip(), "body_empty"),
            (sha256(record.body.encode()).hexdigest() != record.body_sha256, "body_sha256"),
            (not isfinite(hit.score), "score_finite"),
            (not min_similarity <= hit.score <= 1, "score_range"),
            (hit.validation_status != "approved_current", "hit_validation_status"),
            (hit.document_id != str(document.document_id), "hit_document_id"),
            (hit.version != version.version_label, "hit_version"),
            (hit.source_org != document.source_org, "hit_source_org"),
            (hit.source_url != document.source_url, "hit_source_url"),
            (hit.verified_at != verified, "hit_verified_at"),
            (hit.hospital_id != document.hospital_id, "hit_hospital_id"),
        )
        for failed, reason in checks:
            if failed:
                return GuideSourceValidation(block_reason=reason)
        assert verified is not None and document.source_url is not None
        snapshots.append(
            VerifiedGuideSource(
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                section_key=section_key,
                source_org=document.source_org,
                source_url=document.source_url,
                version=version.version_label,
                verified_at=verified,
                hospital_id=document.hospital_id,
                score=hit.score,
                body_sha256=record.body_sha256,
                body=record.body,
            )
        )
    return GuideSourceValidation(sources=tuple(snapshots))
