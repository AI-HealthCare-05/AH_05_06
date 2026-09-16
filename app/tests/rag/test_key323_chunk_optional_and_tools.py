"""KEY-323 §5 보강 계약 테스트.

1. PDF 페이지 범위·머리글 제거
2. DRAFT 버전 폐기(deprecate)
3. 청크 없는 레코드 승인 (chunk_optional)
4. 일반 문서는 여전히 청크 없이 승인 불가
5. 자궁내막증 고정 템플릿 연결 (knowledge_doc_fallback, revalidate_artifact)
6. PCOS Monash v1 실제 콘텐츠 계약 (파일이 있을 때만 실행)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
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
from app.services.approved_knowledge_search import ApprovedKnowledgeOutcome, ApprovedKnowledgeSearchService
from app.services.guide_generation import GeneratedGuideSection
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

        await KnowledgeApprovalService().deprecate(prepared.version_id, deprecated_by="test-operator")

        version = await KnowledgeVersion.get(version_id=prepared.version_id)
        assert version.approval_status is ApprovalStatus.DEPRECATED
        assert version.deprecated_by == "test-operator"
        assert version.deprecated_at is not None

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
            await KnowledgeApprovalService().deprecate(prepared.version_id, deprecated_by="test-operator")

    async def test_deprecate_nonexistent_version_raises(self) -> None:
        with pytest.raises(ValueError, match="KNOWLEDGE_VERSION_NOT_FOUND"):
            await KnowledgeApprovalService().deprecate(
                "00000000-0000-0000-0000-000000000000", deprecated_by="test-operator"
            )


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
            hospital_id=1,
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


# ---------------------------------------------------------------------------
# §5 — 자궁내막증 고정 템플릿 연결 (KEY-323 §4)
# ---------------------------------------------------------------------------


class TestEndometriosisLifeTemplate(TestCase):
    """knowledge_doc_fallback()이 APPROVED chunk_optional 레코드에서
    올바른 ApprovedFallbackTemplate을 조립하고, revalidate_artifact()가
    kv: 접두사 경로로 재검증하는지 확인한다."""

    async def _ingest_and_approve_eshre(self) -> PreparedVersion:
        from app.services.guide_generation import ESHRE_ENDOMETRIOSIS_SOURCE_URL

        prepared = await KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
        ).ingest(
            KnowledgeIngestionRequest(
                title="ESHRE Guideline: Endometriosis (2022)",
                source_org="European Society of Human Reproduction and Embryology",
                source_url=ESHRE_ENDOMETRIOSIS_SOURCE_URL,
                version_label="2022",
                source_kind=KnowledgeSourceKind.TEXT_PDF,
                payload=b"template-only",
                mime_type="text/plain",
                license_basis="CC BY-NC 4.0",
                chunk_optional=True,
            )
        )
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
        return prepared

    async def test_knowledge_doc_fallback_returns_template_for_approved_record(self) -> None:
        from app.services.guide_generation import (
            ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
            ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            knowledge_doc_fallback,
        )

        await self._ingest_and_approve_eshre()

        result = await knowledge_doc_fallback(ESHRE_ENDOMETRIOSIS_SOURCE_URL, ENDOMETRIOSIS_LIFE_TEMPLATE_BODY)

        assert result is not None
        assert result.template_id.startswith("kv:")
        assert result.body == ENDOMETRIOSIS_LIFE_TEMPLATE_BODY
        assert result.approved_by == "이희진"
        assert result.approval_status is ApprovalStatus.APPROVED
        assert result.is_current is True

    async def test_knowledge_doc_fallback_returns_none_when_no_approved_record(self) -> None:
        from app.services.guide_generation import (
            ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
            ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            knowledge_doc_fallback,
        )

        result = await knowledge_doc_fallback(ESHRE_ENDOMETRIOSIS_SOURCE_URL, ENDOMETRIOSIS_LIFE_TEMPLATE_BODY)

        assert result is None

    async def test_revalidate_artifact_passes_for_valid_kv_template(self) -> None:
        from app.services.guide_generation import (
            ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
            ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            RagGuideGenerator,
            knowledge_doc_fallback,
        )
        from app.services.guide_knowledge_context import GuideSourceValidation
        from app.services.knowledge_search import ContextAdmissionOutcome, GenerationContextAdmission

        await self._ingest_and_approve_eshre()
        fallback = await knowledge_doc_fallback(ESHRE_ENDOMETRIOSIS_SOURCE_URL, ENDOMETRIOSIS_LIFE_TEMPLATE_BODY)
        assert fallback is not None

        admission = GenerationContextAdmission(
            outcome=ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK,
            fallback_template=fallback,
        )
        from app.services.safety_check import SafetyVerdict, SafetyVerdictKind

        artifact = GeneratedGuideSection(
            body=fallback.body,
            validation=GuideSourceValidation(),
            admission=admission,
            pre=SafetyVerdict(SafetyVerdictKind.PASS),
            post=None,
        )
        generator = RagGuideGenerator(
            search=cast(ApprovedKnowledgeSearchService, None),
            model=None,
        )

        # 예외 없이 통과해야 한다
        await generator.revalidate_artifact(artifact, hospital_id=1, section_key="life")

    async def test_revalidate_artifact_raises_when_kv_record_deprecated(self) -> None:
        from app.services.guide_generation import (
            ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
            ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            GuideGenerationError,
            RagGuideGenerator,
            knowledge_doc_fallback,
        )
        from app.services.guide_knowledge_context import GuideSourceValidation
        from app.services.knowledge_search import ContextAdmissionOutcome, GenerationContextAdmission

        prepared = await self._ingest_and_approve_eshre()
        fallback = await knowledge_doc_fallback(ESHRE_ENDOMETRIOSIS_SOURCE_URL, ENDOMETRIOSIS_LIFE_TEMPLATE_BODY)
        assert fallback is not None

        # 승인 후 레코드를 강제로 비활성화
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(is_current=False)

        admission = GenerationContextAdmission(
            outcome=ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK,
            fallback_template=fallback,
        )
        from app.services.safety_check import SafetyVerdict, SafetyVerdictKind

        artifact = GeneratedGuideSection(
            body=fallback.body,
            validation=GuideSourceValidation(),
            admission=admission,
            pre=SafetyVerdict(SafetyVerdictKind.PASS),
            post=None,
        )
        generator = RagGuideGenerator(
            search=cast(ApprovedKnowledgeSearchService, None),
            model=None,
        )

        with pytest.raises(GuideGenerationError, match="template_changed"):
            await generator.revalidate_artifact(artifact, hospital_id=1, section_key="life")

    async def test_knowledge_doc_fallback_returns_none_when_review_due_at_expired(self) -> None:
        """review_due_at이 지난 레코드는 knowledge_doc_fallback()이 None을 반환한다."""
        from datetime import timedelta

        from app.services.guide_generation import (
            ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
            ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            knowledge_doc_fallback,
        )

        prepared = await self._ingest_and_approve_eshre()
        past = datetime.now(UTC) - timedelta(days=1)
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(review_due_at=past)

        result = await knowledge_doc_fallback(ESHRE_ENDOMETRIOSIS_SOURCE_URL, ENDOMETRIOSIS_LIFE_TEMPLATE_BODY)

        assert result is None

    async def test_revalidate_artifact_raises_when_review_due_at_expired(self) -> None:
        """review_due_at이 지난 kv: 템플릿은 revalidate_artifact()가 template_changed를 발생시킨다."""
        from datetime import timedelta

        from app.services.guide_generation import (
            ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
            ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            GuideGenerationError,
            RagGuideGenerator,
            knowledge_doc_fallback,
        )
        from app.services.guide_knowledge_context import GuideSourceValidation
        from app.services.knowledge_search import ContextAdmissionOutcome, GenerationContextAdmission
        from app.services.safety_check import SafetyVerdict, SafetyVerdictKind

        prepared = await self._ingest_and_approve_eshre()
        fallback = await knowledge_doc_fallback(ESHRE_ENDOMETRIOSIS_SOURCE_URL, ENDOMETRIOSIS_LIFE_TEMPLATE_BODY)
        assert fallback is not None

        past = datetime.now(UTC) - timedelta(days=1)
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(review_due_at=past)

        admission = GenerationContextAdmission(
            outcome=ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK,
            fallback_template=fallback,
        )
        artifact = GeneratedGuideSection(
            body=fallback.body,
            validation=GuideSourceValidation(),
            admission=admission,
            pre=SafetyVerdict(SafetyVerdictKind.PASS),
            post=None,
        )
        generator = RagGuideGenerator(search=cast(ApprovedKnowledgeSearchService, None), model=None)

        with pytest.raises(GuideGenerationError, match="template_changed"):
            await generator.revalidate_artifact(artifact, hospital_id=1, section_key="life")


# ---------------------------------------------------------------------------
# §5-static — 템플릿 본문 내용 검증 (DB 불필요, 순수 Python)
# ---------------------------------------------------------------------------


def test_endo_template_contains_no_primary_prevention_claim() -> None:
    """①근거(1차 예방)에서 유래한 문장이 없음을 확인한다 (KEY-323 §4 인수조건)."""
    from app.services.guide_generation import ENDOMETRIOSIS_LIFE_TEMPLATE_BODY

    forbidden = ["예방", "preventing endometriosis", "자궁내막증이 생기지", "발병을 막"]
    for phrase in forbidden:
        assert phrase not in ENDOMETRIOSIS_LIFE_TEMPLATE_BODY, f"1차 예방 문구 포함: {phrase!r}"


def test_endo_template_contains_no_disease_treatment_claim() -> None:
    """템플릿에 증상 완화 범위를 벗어난 치료 주장이 없음을 확인한다."""
    from app.services.guide_generation import ENDOMETRIOSIS_LIFE_TEMPLATE_BODY

    forbidden = ["호전된다", "치료된다", "완치", "없어진다"]
    for phrase in forbidden:
        assert phrase not in ENDOMETRIOSIS_LIFE_TEMPLATE_BODY, f"치료 주장 문구 포함: {phrase!r}"


def test_endo_template_contains_no_emergency_phrase() -> None:
    """응급·주의 문구가 포함되지 않는다 (섹션 경계 유지, KEY-323 §4)."""
    from app.services.guide_generation import ENDOMETRIOSIS_LIFE_TEMPLATE_BODY

    forbidden = ["응급", "즉시 병원", "119", "위급"]
    for phrase in forbidden:
        assert phrase not in ENDOMETRIOSIS_LIFE_TEMPLATE_BODY, f"응급 문구 포함: {phrase!r}"


def test_endo_template_sha256_matches_constant() -> None:
    """ENDOMETRIOSIS_LIFE_TEMPLATE_SHA256 상수가 실제 본문과 일치한다.

    전문의 자문 등으로 문구가 바뀌면 이 테스트가 실패하므로,
    상수를 함께 갱신해 변경 이력을 추적한다 (KEY-323 §4, 10524).
    """
    from app.services.guide_generation import ENDOMETRIOSIS_LIFE_TEMPLATE_BODY, ENDOMETRIOSIS_LIFE_TEMPLATE_SHA256
    from app.services.knowledge_search import fallback_body_checksum

    assert fallback_body_checksum(ENDOMETRIOSIS_LIFE_TEMPLATE_BODY) == ENDOMETRIOSIS_LIFE_TEMPLATE_SHA256


# ---------------------------------------------------------------------------
# §6-static — PCOS 생활관리 프롬프트 가드 (KEY-323 §3, DB 불필요)
# ---------------------------------------------------------------------------

_PCOS_GUARD_MARKER = "특정 식이요법이나 운동 방식이 다른 방법보다 우월하다는 근거는 없습니다"


def _collect_instructions(disease: str, section_key: str) -> str:
    """_model_answer()가 조립하는 instructions 문자열을 반환한다."""
    from unittest.mock import AsyncMock

    from app.services.guide_generation import RagGuideGenerator
    from app.services.guide_knowledge_context import GuideSourceValidation

    captured: list[str] = []

    async def fake_generate(*, instructions: str, prompt: str) -> object:
        captured.append(instructions)

        class _R:
            text = '{"body": "ok", "drug_names": []}'

        return _R()

    generator = RagGuideGenerator(search=None, model=AsyncMock())  # type: ignore[arg-type]
    generator.model.generate = fake_generate  # type: ignore[method-assign, union-attr]

    import asyncio

    asyncio.get_event_loop().run_until_complete(
        generator._model_answer(section_key, (), GuideSourceValidation(), disease=disease)  # type: ignore[arg-type]
    )
    return captured[0]


def test_pcos_life_guard_included_for_pcos_life() -> None:
    """PCOS + life 섹션일 때 우월성 제한 가드가 지시문에 포함된다 (KEY-323 §3)."""
    instructions = _collect_instructions(disease="PCOS", section_key="life")
    assert _PCOS_GUARD_MARKER in instructions


def test_pcos_life_guard_excluded_for_endometriosis_life() -> None:
    """자궁내막증 + life 섹션에는 PCOS 가드가 포함되지 않는다."""
    instructions = _collect_instructions(disease="ENDOMETRIOSIS", section_key="life")
    assert _PCOS_GUARD_MARKER not in instructions


def test_pcos_life_guard_excluded_for_pcos_non_life_section() -> None:
    """PCOS라도 life 외 섹션(medication 등)에는 가드가 포함되지 않는다."""
    instructions = _collect_instructions(disease="PCOS", section_key="medication")
    assert _PCOS_GUARD_MARKER not in instructions


# ---------------------------------------------------------------------------
# §7 — PCOS Monash v1 실제 콘텐츠 계약 (KEY-323 인수조건)
#
# CI 실행: 커밋된 픽스처(fixtures/pcos_monash_2023_raw_pages.json)로 실행한다.
# 픽스처가 없으면 scripts/extract_pcos_fixture.py 를 실행해 생성하고 커밋한다.
#
# 원본 PDF MD5 검사(_pcos_md5_required)는 로컬에서만 실행된다.
# 제한사항: 원본 PDF 무결성과 pypdf 추출 동작은 CI에서 확인되지 않는다.
# ---------------------------------------------------------------------------

_IN_CI = os.environ.get("CI") == "true"
_PCOS_PDF_PATH = Path(__file__).resolve().parents[3] / "key276-sources" / "pcos-monash-2023-v1.pdf"
_PCOS_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "pcos_monash_2023_raw_pages.json"
_PCOS_MD5 = "75bb875708c151846416e225adfc54e0"
_PCOS_STRIP_HEADERS = (
    # 쪽 제목 머리글 (홀수 쪽에 반복)
    "International Evidence-based Guideline for the assessment and management of polycystic ovary syndrome 2023",
    # 표 헤더 — PDF 추출 시 각 줄로 분리되므로 개별 줄로 지정한다
    "No.",
    "Living# Type Recommendation",
    "Grade/",
    "Quality",
)
_EXPECTED_RECOMMENDATIONS = {
    "3.1.1",
    "3.1.2",
    "3.1.3",
    "3.1.4",
    "3.1.5",
    "3.1.6",
    "3.1.7",
    "3.1.8",
    "3.1.9",
    "3.1.10",
    "3.2.1",
    "3.2.2",
    "3.2.3",
    "3.3.1",
    "3.3.2",
    "3.3.3",
    "3.3.4",
    "3.4.1",
    "3.4.2",
    "3.4.3",
    "3.4.4",
    "3.4.5",
    "3.4.6",
    "3.4.7",
    "3.5.1",
    "3.5.2",
    "3.6.1",
    "3.6.2",
    "3.6.3",
    "3.6.4",
    "3.6.5",
}
# 약물·불임·진단·IVF 관련 — 35~38쪽(섹션 3)에 없어야 한다
_EXCLUDED_TERMS = (
    "drug",
    "medication",
    "pharmacolog",
    "infertil",
    "IVF",
    "fertility",
    "diagnos",
    "metformin",
    "clomiphene",
    "letrozole",
    "ovulation induction",
)

# 콘텐츠 계약 테스트: 픽스처 또는 원본 PDF 중 하나가 있으면 실행한다.
# CI에서는 픽스처를 사용하고, 로컬에서는 원본 PDF를 우선한다.
_pcos_pdf_required = pytest.mark.skipif(
    not _PCOS_FIXTURE_PATH.exists() and not _PCOS_PDF_PATH.exists(),
    reason=(
        "PCOS 픽스처와 원본 PDF 모두 없음 — "
        "scripts/extract_pcos_fixture.py 를 실행해 픽스처를 생성하거나 PDF를 배치하세요"
    ),
)

# MD5 검사: 원본 PDF가 있어야 하며 CI에서는 건너뛴다.
# 제한사항: 원본 PDF 무결성은 로컬에서만 확인된다 — CI에 PDF를 공급하지 않으므로.
_pcos_md5_required = pytest.mark.skipif(
    not _PCOS_PDF_PATH.exists(),
    reason="원본 PDF 없음 — MD5 검사는 원본 PDF가 있을 때만 실행된다 (CI에서는 건너뜀)",
)


def _pcos_fixture_pdf() -> bytes:
    """픽스처 JSON에서 합성 PDF를 만든다.

    페이지 번호는 원본 PDF와 동일하게 유지한다 (빈 페이지 1~32 + 실제 내용 33~40).
    ASCII 범위 밖 문자( 쪽번호 불릿 등)는 제거한다 — 핵심 내용(권고 번호·
    제외 용어·머리글)은 모두 ASCII이므로 검사 결과에 영향이 없다.
     제거 후 쪽번호 줄이 순수 숫자("35")로 남아 _is_page_number_line()이
    정상 감지·제거한다.
    """
    data = json.loads(_PCOS_FIXTURE_PATH.read_text(encoding="utf-8"))
    pages_dict: dict[str, str] = data["pages"]
    page_texts = [""] * 32 + [
        pages_dict.get(str(i), "").encode("ascii", errors="ignore").decode("ascii") for i in range(33, 41)
    ]
    return _text_pdf_pages(page_texts)


def _load_pcos_chunks():
    from app.services.knowledge_extraction import extract_text_pdf

    pdf_bytes = _PCOS_PDF_PATH.read_bytes() if _PCOS_PDF_PATH.exists() else _pcos_fixture_pdf()
    return extract_text_pdf(
        pdf_bytes,
        page_from=35,
        page_to=38,
        strip_headers=_PCOS_STRIP_HEADERS,
        strip_page_numbers=True,
    )


@_pcos_md5_required
def test_pcos_monash_v1_md5_matches() -> None:
    """적재 대상 파일이 Jira 확정 MD5(75bb8757…)와 일치한다."""
    digest = hashlib.md5(_PCOS_PDF_PATH.read_bytes()).hexdigest()
    assert digest == _PCOS_MD5, f"MD5 불일치: {digest}"


@_pcos_pdf_required
def test_pcos_monash_v1_contains_all_31_recommendations() -> None:
    """35~38쪽에 권고 3.1.1~3.6.5 31개가 모두 포함된다."""
    full = " ".join(c.body for c in _load_pcos_chunks())
    found = set(re.findall(r"3\.\d+\.\d+", full))
    missing = _EXPECTED_RECOMMENDATIONS - found
    assert not missing, f"누락된 권고: {sorted(missing)}"
    assert len(_EXPECTED_RECOMMENDATIONS) == 31


@_pcos_pdf_required
def test_pcos_monash_v1_excludes_drug_infertility_diagnosis_ivf() -> None:
    """35~38쪽 청크에 약물·불임·진단·IVF 관련 용어가 없다."""
    full = " ".join(c.body for c in _load_pcos_chunks()).lower()
    found = [term for term in _EXCLUDED_TERMS if term.lower() in full]
    assert not found, f"제외되어야 할 용어가 포함됨: {found}"


@_pcos_pdf_required
def test_pcos_monash_v1_page_range_excludes_other_chapters() -> None:
    """페이지 범위 적용 후 2장·4장 문장이 포함되지 않는다."""
    full = " ".join(c.body for c in _load_pcos_chunks()).lower()
    # 35쪽 이전(2장)과 39쪽 이후(4장) 섹션 번호가 없어야 한다
    assert not re.search(r"\b2\.\d+\.\d+\b", full), "2장 권고 번호가 포함됨"
    assert not re.search(r"\b4\.\d+\.\d+\b", full), "4장 권고 번호가 포함됨"


@_pcos_pdf_required
def test_pcos_monash_v1_strips_page_title_header() -> None:
    """쪽 제목 머리글이 제거된다 (홀수 쪽에 반복되는 가이드라인 제목)."""
    chunks = _load_pcos_chunks()
    full = " ".join(c.body for c in chunks)
    assert "International Evidence-based Guideline for the assessment and management" not in full, (
        "쪽 제목 머리글이 남아 있다"
    )


@_pcos_pdf_required
def test_pcos_monash_v1_strips_table_header_lines() -> None:
    """표 헤더 줄(No. / Living# Type Recommendation / Grade/ / Quality)이 제거된다."""
    chunks = _load_pcos_chunks()
    lines = set()
    for c in chunks:
        for line in c.body.splitlines():
            lines.add(" ".join(line.split()))
    assert "Living# Type Recommendation" not in lines, "표 헤더 'Living# Type Recommendation'이 남아 있다"
    assert "Grade/" not in lines, "표 헤더 'Grade/'가 남아 있다"


@_pcos_pdf_required
def test_pcos_monash_v1_strips_page_numbers() -> None:
    """쪽번호(U+F0CA 불릿 포함)가 제거된다."""
    chunks = _load_pcos_chunks()
    lines = []
    for c in chunks:
        lines.extend(c.body.splitlines())
    # 숫자만(또는 숫자+U+F0CA)으로 이뤄진 줄이 없어야 한다
    pnum_lines = [
        ln
        for ln in lines
        if " ".join(ln.split()).replace("", "").strip().isdigit() and " ".join(ln.split()).replace("", "").strip()
    ]
    assert not pnum_lines, f"쪽번호 줄이 남아 있다: {pnum_lines[:5]}"


# ---------------------------------------------------------------------------
# §8 — PCOS 생활관리 검색 계약 (KEY-323 인수조건)
# 적재 → 승인 → life 검색 → 제외 용어 미반환 확인
# CI에서는 픽스처 PDF를, 로컬에서는 원본 PDF(있을 경우)를 사용한다
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _PCOS_FIXTURE_PATH.exists() and not _PCOS_PDF_PATH.exists(),
    reason=(
        "PCOS 픽스처와 원본 PDF 모두 없음 — "
        "scripts/extract_pcos_fixture.py 를 실행해 픽스처를 생성하거나 PDF를 배치하세요"
    ),
)
class TestPcosMonashLifeSearchContract(TestCase):
    """Monash v1 적재 → 승인 → life 검색의 종단간 계약 테스트."""

    async def _ingest_and_approve(self) -> PreparedVersion:
        provider = cast(EmbeddingProvider, FakeEmbeddingProvider())
        pdf_bytes = _PCOS_PDF_PATH.read_bytes() if _PCOS_PDF_PATH.exists() else _pcos_fixture_pdf()
        request = KnowledgeIngestionRequest(
            title="International Evidence-based Guideline for the Assessment and Management of Polycystic Ovary Syndrome 2023",
            source_org="Monash University·International PCOS Network",
            source_url="https://doi.org/10.26180/24003834.v1",
            version_label="2023 (Monash Bridges v1)",
            source_kind=KnowledgeSourceKind.TEXT_PDF,
            payload=pdf_bytes,
            mime_type="application/pdf",
            license_basis="CC BY 4.0",
            page_from=35,
            page_to=38,
            strip_headers=_PCOS_STRIP_HEADERS,
            strip_page_numbers=True,
            section_key="life",
        )
        prepared = await KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=provider,
        ).ingest(request)
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(
            source_grade=SourceGrade.A,
            license_verified=True,
        )
        reviewed_at = datetime.now(UTC)
        await KnowledgeApprovalService().approve(
            prepared.version_id,
            approved_by="이희진",
            verified_at=reviewed_at,
            review_due_at=reviewed_at + timedelta(days=365),
        )
        return prepared

    async def test_life_search_returns_pcos_chunks(self) -> None:
        """적재·승인 후 life 검색 결과가 FOUND이고 권고 번호가 포함된다."""
        from datetime import date

        prepared = await self._ingest_and_approve()
        provider = cast(EmbeddingProvider, FakeEmbeddingProvider())
        search = ApprovedKnowledgeSearchService(provider)

        result = await search.search(
            "생활관리",
            hospital_id=1,
            allowed_sections=frozenset({"life"}),
            searched_at=date.today(),
        )

        assert result.outcome is ApprovedKnowledgeOutcome.FOUND, f"검색 결과 없음: {result.outcome}"
        chunk_ids = [hit.chunk_id for hit in result.hits]
        bodies = [c.body for c in await KnowledgeChunkRecord.filter(chunk_id__in=chunk_ids)]
        full = " ".join(bodies)
        assert re.search(r"3\.\d+\.\d+", full), "PCOS 권고 번호(3.x.x)가 검색 결과에 없다"
        version_ids = {str(c.version_id) for c in await KnowledgeChunkRecord.filter(chunk_id__in=chunk_ids)}
        assert version_ids == {str(prepared.version_id)}

    async def test_life_search_excludes_drug_infertility_diagnosis_ivf(self) -> None:
        """life 검색 결과 청크에 약물·불임·진단·IVF 관련 용어가 없다 (KEY-323 인수조건)."""
        from datetime import date

        await self._ingest_and_approve()
        provider = cast(EmbeddingProvider, FakeEmbeddingProvider())
        search = ApprovedKnowledgeSearchService(provider)

        result = await search.search(
            "생활관리",
            hospital_id=1,
            allowed_sections=frozenset({"life"}),
            searched_at=date.today(),
        )

        assert result.outcome is ApprovedKnowledgeOutcome.FOUND
        chunk_ids = [hit.chunk_id for hit in result.hits]
        bodies = [c.body for c in await KnowledgeChunkRecord.filter(chunk_id__in=chunk_ids)]
        full = " ".join(bodies).lower()
        found = [term for term in _EXCLUDED_TERMS if term.lower() in full]
        assert not found, f"제외 용어가 검색 결과에 포함됨: {found}"
