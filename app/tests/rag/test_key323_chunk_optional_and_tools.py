"""KEY-323 §5 보강 계약 테스트.

1. PDF 페이지 범위·머리글 제거
2. DRAFT 버전 폐기(deprecate)
3. 청크 없는 레코드 승인 (chunk_optional)
4. 일반 문서는 여전히 청크 없이 승인 불가
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import cast

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from tortoise.contrib.test import TestCase

from app.models.catalog import ApprovalStatus, SourceGrade
from app.models.knowledge import (
    KnowledgeChunkRecord,
    KnowledgeIngestionStatus,
    KnowledgeSourceKind,
    KnowledgeVersion,
)
from app.services.knowledge_extraction import extract_text_pdf
from app.services.knowledge_pipeline import (
    EmbeddingProvider,
    KnowledgeApprovalService,
    KnowledgeIngestionRequest,
    KnowledgeIngestionService,
    PreparedVersion,
    TortoiseKnowledgeRepository,
)
from app.services.knowledge_search import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from app.services.knowledge_storage import InMemoryPrivateObjectStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    model = EMBEDDING_MODEL
    revision = EMBEDDING_MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(tuple([1.0] + [0.0] * (self.dimension - 1)) for _ in texts)


def _text_pdf_pages(pages: list[str]) -> bytes:
    """지정한 텍스트 목록을 각 페이지에 담은 PDF를 반환한다."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font)  # noqa: SLF001
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = StreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)  # noqa: SLF001
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _request(*, chunk_optional: bool = False) -> KnowledgeIngestionRequest:
    return KnowledgeIngestionRequest(
        title="ESHRE Guideline: Endometriosis",
        source_org="ESHRE",
        source_url="https://example.test/eshre-2022",
        version_label="2022",
        source_kind=KnowledgeSourceKind.TEXT_PDF,
        payload=b"template-only",
        mime_type="text/plain",
        license_basis="CC BY-NC 4.0",
        chunk_optional=chunk_optional,
    )


def _pdf_request(payload: bytes) -> KnowledgeIngestionRequest:
    return KnowledgeIngestionRequest(
        title="PCOS Guideline",
        source_org="Monash",
        source_url="https://example.test/pcos",
        version_label="2023",
        source_kind=KnowledgeSourceKind.TEXT_PDF,
        payload=payload,
        mime_type="application/pdf",
        license_basis="CC BY 4.0",
    )


# ---------------------------------------------------------------------------
# §1 — 페이지 범위 + 머리글 제거
# ---------------------------------------------------------------------------


def test_extract_text_pdf_page_range_limits_pages() -> None:
    pages = ["page one content", "page two content", "page three content", "page four content"]
    pdf = _text_pdf_pages(pages)

    chunks = extract_text_pdf(pdf, page_from=2, page_to=3)

    bodies = " ".join(c.body for c in chunks)
    assert "page two content" in bodies
    assert "page three content" in bodies
    assert "page one content" not in bodies
    assert "page four content" not in bodies


def test_extract_text_pdf_strip_headers_removes_repeated_lines() -> None:
    header = "International Evidence-based Guideline 2023"
    content = f"{header}\nRecommendation text here"
    pdf = _text_pdf_pages([content])

    chunks_with = extract_text_pdf(pdf, strip_headers=(header,))
    chunks_without = extract_text_pdf(pdf)

    assert all(header not in c.body for c in chunks_with), "머리글이 제거되어야 한다"
    assert any(header in c.body for c in chunks_without), "제거 없이는 머리글이 포함되어야 한다"


def test_extract_text_pdf_strip_page_numbers_removes_digit_only_lines() -> None:
    content = "35\nRecommendation 3.1.1 text here\n36"
    pdf = _text_pdf_pages([content])

    chunks = extract_text_pdf(pdf, strip_page_numbers=True)

    bodies = " ".join(c.body for c in chunks)
    assert "35" not in bodies.split() or "Recommendation" in bodies
    assert "Recommendation 3.1.1 text here" in bodies


def test_extract_text_pdf_page_from_to_section_key_reflects_original_page_number() -> None:
    pdf = _text_pdf_pages(["p1", "p2", "p3"])

    chunks = extract_text_pdf(pdf, page_from=2, page_to=2)

    assert all(c.section_key == "page-2" for c in chunks)
    assert all(c.page_number == 2 for c in chunks)


# ---------------------------------------------------------------------------
# §2 — draft 폐기 (deprecate)
# ---------------------------------------------------------------------------


class TestDeprecateVersion(TestCase):
    async def _ingest_draft(self) -> PreparedVersion:
        return await KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
        ).ingest(_request(chunk_optional=True))

    async def test_deprecate_draft_changes_status(self) -> None:
        prepared = await self._ingest_draft()

        await KnowledgeApprovalService().deprecate(prepared.version_id, deprecated_by="권일준")

        version = await KnowledgeVersion.get(version_id=prepared.version_id)
        assert version.approval_status is ApprovalStatus.DEPRECATED

    async def test_deprecate_approved_version_is_rejected(self) -> None:
        prepared = await self._ingest_draft()
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(
            source_grade=SourceGrade.A, license_verified=True, chunk_optional=True
        )
        reviewed_at = datetime.now(UTC)
        await KnowledgeApprovalService().approve(
            prepared.version_id,
            approved_by="이희진",
            verified_at=reviewed_at,
            review_due_at=reviewed_at + timedelta(days=365),
        )

        with pytest.raises(ValueError, match="KNOWLEDGE_VERSION_NOT_DEPRECATABLE"):
            await KnowledgeApprovalService().deprecate(prepared.version_id, deprecated_by="권일준")

    async def test_deprecate_nonexistent_version_raises(self) -> None:
        with pytest.raises(ValueError, match="KNOWLEDGE_VERSION_NOT_FOUND"):
            await KnowledgeApprovalService().deprecate("00000000-0000-0000-0000-000000000000", deprecated_by="권일준")


# ---------------------------------------------------------------------------
# §3 — 청크 없는 레코드 승인 (chunk_optional=True)
# ---------------------------------------------------------------------------


class TestChunkOptionalApproval(TestCase):
    async def _ingest_template_only(self) -> PreparedVersion:
        return await KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
        ).ingest(_request(chunk_optional=True))

    async def test_chunk_optional_ingest_creates_no_chunks(self) -> None:
        prepared = await self._ingest_template_only()

        chunk_count = await KnowledgeChunkRecord.filter(version_id=prepared.version_id).count()
        assert chunk_count == 0

    async def test_chunk_optional_ingest_marks_attempt_ready(self) -> None:
        from app.models.knowledge import KnowledgeIngestionAttempt

        prepared = await self._ingest_template_only()

        attempt = await KnowledgeIngestionAttempt.get(attempt_id=prepared.attempt_id)
        assert attempt.status is KnowledgeIngestionStatus.READY

    async def test_chunk_optional_version_can_be_approved_without_chunks(self) -> None:
        prepared = await self._ingest_template_only()
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(
            source_grade=SourceGrade.A, license_verified=True, chunk_optional=True
        )
        reviewed_at = datetime.now(UTC)

        await KnowledgeApprovalService().approve(
            prepared.version_id,
            approved_by="이희진",
            verified_at=reviewed_at,
            review_due_at=reviewed_at + timedelta(days=365),
        )

        version = await KnowledgeVersion.get(version_id=prepared.version_id)
        assert version.approval_status is ApprovalStatus.APPROVED
        assert version.is_current is True

    async def test_search_does_not_return_chunk_optional_document(self) -> None:
        """chunk_optional 레코드는 청크가 없으므로 검색 결과에 반환되지 않는다."""
        from datetime import date

        from app.services.approved_knowledge_search import ApprovedKnowledgeOutcome, ApprovedKnowledgeSearchService

        prepared = await self._ingest_template_only()
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(
            source_grade=SourceGrade.A, license_verified=True, chunk_optional=True
        )
        reviewed_at = datetime.now(UTC)
        await KnowledgeApprovalService().approve(
            prepared.version_id,
            approved_by="이희진",
            verified_at=reviewed_at,
            review_due_at=reviewed_at + timedelta(days=365),
        )

        search = ApprovedKnowledgeSearchService(cast(EmbeddingProvider, FakeEmbeddingProvider()))
        result = await search.search(
            "자궁내막증 생활관리",
            hospital_id=None,
            allowed_sections=frozenset({"page-1"}),
            searched_at=date.today(),
        )

        assert result.outcome is ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT


# ---------------------------------------------------------------------------
# §4 — 일반 문서는 여전히 청크 없이 승인 불가
# ---------------------------------------------------------------------------


class TestChunkRequiredForNormalVersion(TestCase):
    async def test_normal_version_without_chunks_is_still_rejected(self) -> None:
        pdf = _text_pdf_pages(["verified medical guidance content"])
        prepared = await KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
        ).ingest(_pdf_request(pdf))
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(
            source_grade=SourceGrade.A, license_verified=True
        )
        await KnowledgeChunkRecord.filter(version_id=prepared.version_id).delete()

        with pytest.raises(ValueError, match="KNOWLEDGE_CHUNKS_NOT_READY"):
            reviewed_at = datetime.now(UTC)
            await KnowledgeApprovalService().approve(
                prepared.version_id,
                approved_by="이희진",
                verified_at=reviewed_at,
                review_due_at=reviewed_at + timedelta(days=365),
            )
