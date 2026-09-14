from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from math import isfinite
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from tortoise.contrib.test import TestCase

from app.models.catalog import ApprovalStatus, SourceGrade
from app.models.knowledge import KnowledgeChunkRecord, KnowledgeDocument, KnowledgeSourceKind, KnowledgeVersion
from app.services.approved_knowledge_search import (
    ApprovedKnowledgeHit,
    ApprovedKnowledgeOutcome,
    ApprovedKnowledgeResult,
)
from app.services.guide_knowledge_context import revalidate_guide_sources


class TestDatabaseRevalidation(TestCase):
    async def test_revocation_after_search_is_read_from_database(self):
        document = await KnowledgeDocument.create(
            source_key=str(uuid4()),
            title="합성 자료",
            source_org="합성 기관",
            source_url="https://example.invalid",
            source_kind=KnowledgeSourceKind.TEXT_PDF,
            hospital_id=1,
        )
        version = await KnowledgeVersion.create(
            document=document,
            version_label="v1",
            source_sha256="a" * 64,
            source_object_key="synthetic/test.pdf",
            source_mime_type="application/pdf",
            extractor_version="test",
            approval_status=ApprovalStatus.APPROVED,
            is_current=True,
            current_approved_key=str(document.document_id),
            source_grade=SourceGrade.A,
            license_verified=True,
            approved_by="합성 검토자",
            approved_at=datetime(2026, 9, 1),
            verified_at=datetime(2026, 9, 1),
        )
        chunk = await KnowledgeChunkRecord.create(
            version=version,
            section_key="medication",
            position=0,
            body="합성 근거",
            body_sha256=sha256("합성 근거".encode()).hexdigest(),
            embedding=[1.0],
            embedding_model="test",
            embedding_revision="test",
            embedding_dimension=1,
        )
        captured = ApprovedKnowledgeResult(
            ApprovedKnowledgeOutcome.FOUND,
            (
                ApprovedKnowledgeHit(
                    str(document.document_id),
                    str(chunk.chunk_id),
                    document.source_org,
                    document.source_url,
                    "v1",
                    date(2026, 9, 1),
                    1,
                    0.9,
                ),
            ),
        )
        before = await revalidate_guide_sources(
            captured,
            hospital_id=1,
            section_key="medication",
            checked_at=date(2026, 9, 10),
        )
        assert len(before.sources) == 1
        # DB를 직접 변경한다. 캡처한 검색 결과와 메모리 version 인스턴스는 그대로다.
        await KnowledgeVersion.filter(version_id=version.version_id).update(is_current=False)
        assert version.is_current is True
        after = await revalidate_guide_sources(
            captured,
            hospital_id=1,
            section_key="medication",
            checked_at=date(2026, 9, 10),
        )
        assert after.sources == ()
        assert after.block_reason == "is_current"


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


async def resolve(record, hits, **kwargs):
    with patch("app.services.guide_knowledge_context.KnowledgeChunkRecord.filter") as query:
        query.return_value.prefetch_related = AsyncMock(return_value=[record])
        return await revalidate_guide_sources(
            ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.FOUND, tuple(hits)),
            hospital_id=1,
            section_key="medication",
            checked_at=date(2026, 9, 10),
            **kwargs,
        )


async def test_snapshot_does_not_follow_source_edits():
    record, hit = candidate()
    snapshots = await resolve(record, [hit])
    assert snapshots.block_reason is None
    assert len(snapshots.sources) == 1
    record.body = "수정된 근거"
    assert snapshots.sources[0].body == "합성 근거"
    assert "합성 근거" not in repr(snapshots.sources[0])
    assert (await resolve(record, [hit])).block_reason == "body_sha256"


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
    expected = "verified_at_future" if key == "verified_at" and value is not None else key
    assert (await resolve(record, [hit])).block_reason == expected


@pytest.mark.parametrize("key,value", [("hospital_id", 2), ("source_url", ""), ("source_org", "")])
async def test_changed_document_blocks(key, value):
    record, hit = candidate()
    setattr(record.version.document, key, value)
    expected = "hospital_scope" if key == "hospital_id" else key
    assert (await resolve(record, [hit])).block_reason == expected


@pytest.mark.parametrize("score", [0.71, float("nan"), float("inf"), 1.1])
async def test_invalid_score_blocks(score):
    record, hit = candidate()
    expected = "score_finite" if not isfinite(score) else "score_range"
    assert (await resolve(record, [replace(hit, score=score)])).block_reason == expected


async def test_missing_or_duplicate_hit_blocks_whole_set():
    record, hit = candidate()
    assert (await resolve(record, [hit, replace(hit, chunk_id=str(uuid4()))])).block_reason == "missing_chunk"
    assert (await resolve(record, [hit, hit])).block_reason == "duplicate_chunk_id"


async def test_section_mismatch_blocks():
    record, hit = candidate()
    record.section_key = "life"
    assert (await resolve(record, [hit])).block_reason == "section_key"


@pytest.mark.parametrize(
    "outcome",
    [
        ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT,
        ApprovedKnowledgeOutcome.SOURCE_CONFLICT,
        ApprovedKnowledgeOutcome.INDEX_INVALID,
    ],
)
async def test_search_failure_reason_is_preserved(outcome):
    result = await revalidate_guide_sources(
        ApprovedKnowledgeResult(outcome),
        hospital_id=1,
        section_key="medication",
        checked_at=date(2026, 9, 10),
    )
    assert result.sources == ()
    assert result.block_reason == outcome.value


async def test_field_mismatch_reason_is_specific():
    record, hit = candidate()
    record.version.is_current = False
    result = await resolve(record, [hit])
    assert result.sources == ()
    assert result.block_reason == "is_current"


async def test_similarity_override_is_shared():
    record, hit = candidate()
    with patch("app.services.guide_knowledge_context.KnowledgeChunkRecord.filter") as query:
        query.return_value.prefetch_related = AsyncMock(return_value=[record])
        result = await revalidate_guide_sources(
            ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.FOUND, (replace(hit, score=0.7),)),
            hospital_id=1,
            section_key="medication",
            checked_at=date(2026, 9, 10),
            min_similarity=0.65,
        )
    assert result.block_reason is None
    assert len(result.sources) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("document_id", "different-document"),
        ("version", "different-version"),
        ("source_org", "다른 기관"),
        ("source_url", "https://example.invalid/changed"),
        ("verified_at", date(2026, 9, 2)),
        ("hospital_id", 2),
        ("validation_status", "unverified"),
    ],
)
async def test_hit_mismatch_has_exact_reason(key, value):
    record, hit = candidate()
    result = await resolve(record, [replace(hit, **{key: value})])
    assert result.sources == ()
    assert result.block_reason == "hit_" + key


@pytest.mark.parametrize(
    "hospital_id,expected",
    [
        (None, None),
        (1, None),
        (2, "hospital_scope"),
    ],
)
async def test_hospital_scope_independently(hospital_id, expected):
    record, hit = candidate()
    record.version.document.hospital_id = hospital_id
    # DB와 hit는 일치시켜 hit_hospital_id가 대신 차단하지 않게 한다.
    result = await resolve(record, [replace(hit, hospital_id=hospital_id)])
    assert result.block_reason == expected
    assert bool(result.sources) == (expected is None)


@pytest.mark.parametrize(
    "target,key,value,expected",
    [
        ("version", "approved_at", datetime(2026, 10, 1), "approved_at_future"),
        ("document", "source_url", None, "source_url"),
        ("document", "source_url", "   ", "source_url_blank"),
        ("document", "source_org", "   ", "source_org"),
        ("record", "body", "   ", "body_empty"),
    ],
)
async def test_missing_guards_have_exact_reason(target, key, value, expected):
    record, hit = candidate()
    owner = {"version": record.version, "document": record.version.document, "record": record}[target]
    setattr(owner, key, value)
    result = await resolve(record, [hit])
    assert result.sources == ()
    assert result.block_reason == expected


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
async def test_invalid_threshold_has_exact_reason(threshold):
    record, hit = candidate()
    result = await resolve(record, [hit], min_similarity=threshold)
    assert result.sources == ()
    assert result.block_reason == "invalid_min_similarity"


@pytest.mark.parametrize("chunk_id", ["not-a-uuid", "", None])
async def test_invalid_chunk_id_has_exact_reason(chunk_id):
    record, hit = candidate()
    result = await resolve(record, [replace(hit, chunk_id=chunk_id)])
    assert result.sources == ()
    assert result.block_reason == "invalid_chunk_id"


async def test_empty_found_is_not_no_evidence():
    record, _ = candidate()
    result = await resolve(record, [])
    assert result.sources == ()
    assert result.block_reason == "empty_found_hits"
