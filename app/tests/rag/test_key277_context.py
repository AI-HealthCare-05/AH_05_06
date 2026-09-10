from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.catalog import ApprovalStatus, SourceGrade
from app.services.approved_knowledge_search import (
    ApprovedKnowledgeHit,
    ApprovedKnowledgeOutcome,
    ApprovedKnowledgeResult,
)
from app.services.guide_knowledge_context import revalidate_guide_sources


def candidate():
    document = SimpleNamespace(
        document_id=uuid4(), hospital_id=1, source_org="합성 기관", source_url="https://example.invalid"
    )
    version = SimpleNamespace(
        document=document,
        approval_status=ApprovalStatus.APPROVED,
        is_current=True,
        current_approved_key=str(document.document_id),
        source_grade=SourceGrade.A,
        license_verified=True,
        approved_by="합성 검토자",
        approved_at=datetime(2026, 9, 1),
        verified_at=datetime(2026, 9, 1),
        review_due_at=datetime(2026, 10, 1),
        version_label="v1",
    )
    record = SimpleNamespace(
        chunk_id=uuid4(),
        version=version,
        section_key="medication",
        body="합성 근거",
        body_sha256=sha256("합성 근거".encode()).hexdigest(),
    )
    hit = ApprovedKnowledgeHit(
        str(document.document_id),
        str(record.chunk_id),
        document.source_org,
        document.source_url,
        "v1",
        date(2026, 9, 1),
        1,
        0.9,
    )
    return record, hit


async def resolve(record, hits):
    with patch("app.services.guide_knowledge_context.KnowledgeChunkRecord.filter") as query:
        query.return_value.prefetch_related = AsyncMock(return_value=[record])
        return await revalidate_guide_sources(
            ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.FOUND, tuple(hits)),
            hospital_id=1,
            section_key="medication",
            checked_at=date(2026, 9, 10),
        )


async def test_snapshot_does_not_follow_source_edits():
    record, hit = candidate()
    snapshots = await resolve(record, [hit])
    assert len(snapshots) == 1
    record.body = "수정된 근거"
    assert snapshots[0].body == "합성 근거"
    assert "합성 근거" not in repr(snapshots[0])
    assert await resolve(record, [hit]) == ()


@pytest.mark.parametrize(
    "key,value",
    [
        ("approval_status", ApprovalStatus.DRAFT),
        ("approval_status", ApprovalStatus.DEPRECATED),
        ("is_current", False),
        ("current_approved_key", None),
        ("source_grade", SourceGrade.C),
        ("license_verified", False),
        ("approved_by", None),
        ("approved_at", None),
        ("verified_at", None),
        ("verified_at", datetime(2026, 10, 1)),
        ("review_due_at", datetime(2026, 9, 9)),
    ],
)
async def test_changed_approval_blocks(key, value):
    record, hit = candidate()
    setattr(record.version, key, value)
    assert await resolve(record, [hit]) == ()


@pytest.mark.parametrize("key,value", [("hospital_id", 2), ("source_url", ""), ("source_org", "")])
async def test_changed_document_blocks(key, value):
    record, hit = candidate()
    setattr(record.version.document, key, value)
    assert await resolve(record, [hit]) == ()


@pytest.mark.parametrize("score", [0.71, float("nan"), float("inf"), 1.1])
async def test_invalid_score_blocks(score):
    record, hit = candidate()
    assert await resolve(record, [replace(hit, score=score)]) == ()


async def test_missing_or_duplicate_hit_blocks_whole_set():
    record, hit = candidate()
    assert await resolve(record, [hit, replace(hit, chunk_id=str(uuid4()))]) == ()
    assert await resolve(record, [hit, hit]) == ()


async def test_section_mismatch_blocks():
    record, hit = candidate()
    record.section_key = "life"
    assert await resolve(record, [hit]) == ()
