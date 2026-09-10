"""KEY-277 연결 준비: 검색 후 현재 DB를 재검증한 근거 스냅샷.

LLM 호출·GuideService 배선은 하지 않는다. KEY-75 상태기계와 선행 평가가
확정된 뒤 호출자가 이 결과를 섹션별로 저장하고 사용하는 계약이다.
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


async def revalidate_guide_sources(
    result: ApprovedKnowledgeResult,
    *,
    hospital_id: int,
    section_key: str,
    checked_at: date,
) -> tuple[VerifiedGuideSource, ...]:
    """하나라도 불일치하면 전체를 차단해 부분 근거로 생성하지 않는다."""
    if result.outcome is not ApprovedKnowledgeOutcome.FOUND or not result.hits:
        return ()
    try:
        ids = [UUID(hit.chunk_id) for hit in result.hits]
    except (ValueError, TypeError, AttributeError):
        return ()
    if len(set(ids)) != len(ids):
        return ()
    records = await KnowledgeChunkRecord.filter(chunk_id__in=ids).prefetch_related("version__document")
    by_id = {str(record.chunk_id): record for record in records}
    snapshots = []
    for hit in result.hits:
        record = by_id.get(hit.chunk_id)
        if record is None:
            return ()
        version = record.version
        document = version.document
        verified = version.verified_at.date() if version.verified_at else None
        if (
            version.approval_status is not ApprovalStatus.APPROVED
            or not version.is_current
            or version.current_approved_key != str(document.document_id)
            or version.source_grade is not SourceGrade.A
            or not version.license_verified
            or not version.approved_by
            or version.approved_at is None
            or version.approved_at.date() > checked_at
            or verified is None
            or verified > checked_at
            or (version.review_due_at is not None and version.review_due_at.date() < checked_at)
            or document.hospital_id not in (None, hospital_id)
            or record.section_key != section_key
            or not document.source_org.strip()
            or not document.source_url
            or not document.source_url.strip()
            or not record.body.strip()
            or sha256(record.body.encode()).hexdigest() != record.body_sha256
            or not isfinite(hit.score)
            or not DEFAULT_MIN_SIMILARITY <= hit.score <= 1
            or hit.validation_status != "approved_current"
            or hit.document_id != str(document.document_id)
            or hit.version != version.version_label
            or hit.source_org != document.source_org
            or hit.source_url != document.source_url
            or hit.verified_at != verified
            or hit.hospital_id != document.hospital_id
        ):
            return ()
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
    return tuple(snapshots)
