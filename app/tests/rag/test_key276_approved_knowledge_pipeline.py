"""KEY-276 승인 의료지식 적재·검색 안전 계약."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from tortoise.contrib.test import TestCase

from app.models.catalog import ApprovalStatus, SourceGrade
from app.models.knowledge import (
    KnowledgeChunkRecord,
    KnowledgeIngestionAttempt,
    KnowledgeIngestionStatus,
    KnowledgeSourceKind,
    KnowledgeVersion,
)
from app.services.approved_knowledge_search import ApprovedKnowledgeOutcome, ApprovedKnowledgeSearchService
from app.services.knowledge_extraction import MAX_CHUNK_CHARS, ExtractedChunk, OcrTextBlock, chunk_text
from app.services.knowledge_pipeline import (
    EmbeddingProvider,
    KnowledgeApprovalService,
    KnowledgeIngestionRequest,
    KnowledgeIngestionService,
    PreparedVersion,
    TortoiseKnowledgeRepository,
)
from app.services.knowledge_search import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from app.services.knowledge_storage import InMemoryPrivateObjectStore, validate_private_object_key

ROOT = Path(__file__).resolve().parents[3]


def _text_pdf(text: str) -> bytes:
    """pypdf가 실제로 읽는 한 페이지 텍스트 PDF fixture를 메모리에서 만든다."""

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)  # noqa: SLF001 - fixture PDF의 최소 object graph
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = StreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)  # noqa: SLF001
    from io import BytesIO

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _blank_pdf(page_count: int) -> bytes:
    from io import BytesIO

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class FakeEmbeddingProvider:
    model = EMBEDDING_MODEL
    revision = EMBEDDING_MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(tuple([1.0] + [0.0] * (self.dimension - 1)) for _ in texts)


class FakeOcrExtractor:
    async def extract(self, payload: bytes, mime_type: str) -> tuple[OcrTextBlock, ...]:
        assert payload.startswith(b"scan")
        assert mime_type == "image/png"
        return (
            OcrTextBlock(
                text="응급 증상이 있으면 즉시 의료기관에 문의합니다.",
                page_number=1,
                bounding_boxes=({"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0},),
                confidence=0.99,
            ),
        )


@dataclass
class AttemptState:
    status: KnowledgeIngestionStatus
    error_code: str | None = None
    retryable: bool = False


class FakeRepository:
    def __init__(self) -> None:
        self.versions: dict[tuple[str, str], PreparedVersion] = {}
        self.attempts: dict[str, AttemptState] = {}
        self.chunks: dict[str, list[ExtractedChunk]] = {}

    async def prepare(self, request, *, source_key, source_sha256, object_key):
        key = (source_key, request.version_label)
        if key not in self.versions:
            self.versions[key] = PreparedVersion(str(uuid4()), str(uuid4()), str(uuid4()), object_key)
        prior = self.versions[key]
        prepared = PreparedVersion(prior.document_id, prior.version_id, str(uuid4()), object_key)
        self.attempts[prepared.attempt_id] = AttemptState(KnowledgeIngestionStatus.PENDING)
        return prepared

    async def store_chunks(self, prepared, chunks, vectors, provider):
        assert len(chunks) == len(vectors)
        assert provider.dimension == EMBEDDING_DIMENSION
        self.chunks[prepared.version_id] = list(chunks)

    async def mark_attempt(self, attempt_id, status, *, error_code=None, retryable=False):
        self.attempts[attempt_id] = AttemptState(status, error_code, retryable)


def _request(kind: KnowledgeSourceKind, payload: bytes, mime_type: str) -> KnowledgeIngestionRequest:
    return KnowledgeIngestionRequest(
        title=f"검증 자료 {kind.value}",
        source_org="질병관리청",
        source_url=f"https://example.test/{kind.value}",
        version_label="2026-09",
        source_kind=kind,
        payload=payload,
        mime_type=mime_type,
        hospital_id=1,
        license_basis="공공누리 제1유형",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "payload", "mime_type"),
    (
        (KnowledgeSourceKind.TEXT_PDF, _text_pdf("verified medical guidance"), "application/pdf"),
        (KnowledgeSourceKind.SCANNED_DOCUMENT, b"scan-image-fixture", "image/png"),
        (
            KnowledgeSourceKind.STRUCTURED_API,
            b'{"guidance":{"title":"verified","steps":["one","two"]}}',
            "application/json",
        ),
    ),
)
async def test_three_source_kinds_share_one_private_ingestion_contract(kind, payload, mime_type) -> None:
    repository = FakeRepository()
    store = InMemoryPrivateObjectStore()
    service = KnowledgeIngestionService(
        repository=repository,
        object_store=store,
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
        ocr_extractor=FakeOcrExtractor(),
    )

    prepared = await service.ingest(_request(kind, payload, mime_type))

    assert prepared.source_object_key.startswith("knowledge/1/")
    assert "://" not in prepared.source_object_key
    assert store.objects[prepared.source_object_key] == (payload, mime_type)
    assert repository.attempts[prepared.attempt_id].status is KnowledgeIngestionStatus.READY
    assert repository.chunks[prepared.version_id]


@pytest.mark.asyncio
async def test_multi_page_scanned_pdf_fails_closed_before_partial_ocr() -> None:
    service = KnowledgeIngestionService(
        repository=FakeRepository(),
        object_store=InMemoryPrivateObjectStore(),
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
        ocr_extractor=FakeOcrExtractor(),
    )

    with pytest.raises(ValueError, match="OCR_MULTIPAGE_NOT_SUPPORTED"):
        await service.ingest(_request(KnowledgeSourceKind.SCANNED_DOCUMENT, _blank_pdf(2), "application/pdf"))


@pytest.mark.asyncio
async def test_reingesting_same_document_version_replaces_instead_of_duplicating_chunks() -> None:
    repository = FakeRepository()
    service = KnowledgeIngestionService(
        repository=repository,
        object_store=InMemoryPrivateObjectStore(),
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
    )
    request = _request(
        KnowledgeSourceKind.STRUCTURED_API,
        b'{"verified":true,"guidance":"same"}',
        "application/json",
    )

    first = await service.ingest(request)
    second = await service.ingest(request)

    assert first.version_id == second.version_id
    assert len(repository.versions) == 1
    assert len(repository.chunks[first.version_id]) == 1


class FailingStore(InMemoryPrivateObjectStore):
    async def put(self, object_key: str, payload: bytes, content_type: str) -> None:
        raise RuntimeError(f"credentials-and-raw-{payload.decode()}")


@pytest.mark.asyncio
async def test_storage_failure_is_retryable_without_raw_source_in_persisted_error() -> None:
    repository = FakeRepository()
    service = KnowledgeIngestionService(
        repository=repository,
        object_store=FailingStore(),
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
    )
    raw_secret = b"do-not-persist-this-source"

    with pytest.raises(RuntimeError):
        await service.ingest(_request(KnowledgeSourceKind.STRUCTURED_API, raw_secret, "application/json"))

    state = next(iter(repository.attempts.values()))
    assert state.status is KnowledgeIngestionStatus.RETRYABLE_FAILURE
    assert state.retryable is True
    assert raw_secret.decode() not in (state.error_code or "")


def test_chunker_obeys_key82_size_contract() -> None:
    chunks = chunk_text("가" * 1800, section_key="warning")
    assert chunks
    assert all(0 < len(chunk.body) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))


def test_private_store_rejects_urls_and_path_traversal() -> None:
    with pytest.raises(ValueError, match="PUBLIC_OBJECT_URL_FORBIDDEN"):
        validate_private_object_key("https://public.example/source.pdf")
    with pytest.raises(ValueError, match="INVALID_PRIVATE_OBJECT_KEY"):
        validate_private_object_key("knowledge/../secret")


def test_migration_and_model_registration_exist_without_generation_connection() -> None:
    database_config = (ROOT / "app/core/db/databases.py").read_text(encoding="utf-8")
    migration = next((ROOT / "app/core/db/migrations/models").glob("44_*key276*.py")).read_text(encoding="utf-8")
    pipeline = (ROOT / "app/services/knowledge_pipeline.py").read_text(encoding="utf-8")

    assert '"app.models.knowledge"' in database_config
    for table in (
        "knowledge_document",
        "knowledge_version",
        "knowledge_chunk",
        "knowledge_ingestion_attempt",
    ):
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in migration
    assert "MODELS_STATE" in migration
    assert "Guide" not in pipeline and "chatbot" not in pipeline.lower()


class TestDbApprovedKnowledgePipeline(TestCase):
    @staticmethod
    def _provider() -> EmbeddingProvider:
        return cast(EmbeddingProvider, FakeEmbeddingProvider())

    async def _ingest(self, request: KnowledgeIngestionRequest | None = None) -> PreparedVersion:
        return await KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=self._provider(),
        ).ingest(
            request
            or _request(
                KnowledgeSourceKind.STRUCTURED_API,
                b'{"emergency":"seek verified medical care"}',
                "application/json",
            )
        )

    @staticmethod
    async def _make_approvable(version_id: str) -> None:
        await KnowledgeVersion.filter(version_id=version_id).update(
            source_grade=SourceGrade.A,
            license_verified=True,
        )

    @staticmethod
    async def _approve(version_id: str, *, reviewer: str = "medical-reviewer") -> None:
        reviewed_at = datetime.now(UTC)
        await KnowledgeApprovalService().approve(
            version_id,
            approved_by=reviewer,
            verified_at=reviewed_at,
            review_due_at=reviewed_at + timedelta(days=30),
        )

    async def test_only_approved_current_in_scope_version_returns_trace_metadata(self) -> None:
        provider = cast(EmbeddingProvider, FakeEmbeddingProvider())
        ingestion = KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=InMemoryPrivateObjectStore(),
            embedding_provider=provider,
        )
        prepared = await ingestion.ingest(
            _request(
                KnowledgeSourceKind.STRUCTURED_API,
                b'{"emergency":"seek verified medical care"}',
                "application/json",
            )
        )
        search = ApprovedKnowledgeSearchService(provider)

        before_approval = await search.search(
            "emergency",
            hospital_id=1,
            allowed_sections=frozenset({"api-snapshot"}),
            searched_at=date.today(),
            min_similarity=0.9,
        )
        assert before_approval.outcome is ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT

        await KnowledgeVersion.filter(version_id=prepared.version_id).update(
            source_grade=SourceGrade.A,
            license_verified=True,
        )
        await KnowledgeApprovalService().approve(
            prepared.version_id,
            approved_by="medical-reviewer",
            verified_at=datetime.now(UTC),
            review_due_at=datetime.now(UTC) + timedelta(days=30),
        )

        result = await search.search(
            "emergency",
            hospital_id=1,
            allowed_sections=frozenset({"api-snapshot"}),
            searched_at=date.today(),
            min_similarity=0.9,
        )
        assert result.outcome is ApprovedKnowledgeOutcome.FOUND
        assert len(result.hits) == 1
        hit = result.hits[0]
        assert hit.document_id == prepared.document_id
        assert hit.chunk_id == str((await KnowledgeChunkRecord.get(version_id=prepared.version_id)).chunk_id)
        assert hit.source_org == "질병관리청"
        assert hit.source_url.startswith("https://")
        assert hit.version == "2026-09"
        assert hit.hospital_id == 1
        assert hit.validation_status == "approved_current"

        other_hospital = await search.search(
            "emergency",
            hospital_id=2,
            allowed_sections=frozenset({"api-snapshot"}),
            searched_at=date.today(),
            min_similarity=0.9,
        )
        assert other_hospital.outcome is ApprovedKnowledgeOutcome.NO_VERIFIED_CONTEXT

    async def test_approval_rejects_non_a_grade(self) -> None:
        prepared = await self._ingest()

        with pytest.raises(ValueError, match="SOURCE_GRADE_NOT_APPROVABLE"):
            await self._approve(prepared.version_id)

    async def test_approval_rejects_unverified_license_or_source(self) -> None:
        prepared = await self._ingest()
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(source_grade=SourceGrade.A)

        with pytest.raises(ValueError, match="SOURCE_VERIFICATION_INCOMPLETE"):
            await self._approve(prepared.version_id)

    async def test_approval_rejects_missing_chunks(self) -> None:
        prepared = await self._ingest()
        await self._make_approvable(prepared.version_id)
        await KnowledgeChunkRecord.filter(version_id=prepared.version_id).delete()

        with pytest.raises(ValueError, match="KNOWLEDGE_CHUNKS_NOT_READY"):
            await self._approve(prepared.version_id)

    async def test_approval_rejects_non_ready_ingestion(self) -> None:
        prepared = await self._ingest()
        await self._make_approvable(prepared.version_id)
        await KnowledgeIngestionAttempt.filter(version_id=prepared.version_id).update(
            status=KnowledgeIngestionStatus.FAILED
        )

        with pytest.raises(ValueError, match="KNOWLEDGE_INGESTION_NOT_READY"):
            await self._approve(prepared.version_id)

    async def test_approval_rejects_expired_review_window(self) -> None:
        prepared = await self._ingest()
        await self._make_approvable(prepared.version_id)
        reviewed_at = datetime.now(UTC) - timedelta(days=2)

        with pytest.raises(ValueError, match="REVIEW_ALREADY_EXPIRED"):
            await KnowledgeApprovalService().approve(
                prepared.version_id,
                approved_by="medical-reviewer",
                verified_at=reviewed_at,
                review_due_at=reviewed_at + timedelta(days=1),
            )

    async def test_approved_current_chunks_cannot_be_replaced(self) -> None:
        prepared = await self._ingest()
        await self._make_approvable(prepared.version_id)
        await self._approve(prepared.version_id)
        original = await KnowledgeChunkRecord.get(version_id=prepared.version_id)
        replacement = ExtractedChunk(section_key="api-snapshot", body="unreviewed replacement", position=0)
        vectors = await self._provider().embed((replacement.body,))

        with pytest.raises(ValueError, match="APPROVED_VERSION_IMMUTABLE"):
            await TortoiseKnowledgeRepository().store_chunks(
                prepared,
                (replacement,),
                vectors,
                self._provider(),
            )

        persisted = await KnowledgeChunkRecord.get(version_id=prepared.version_id)
        assert persisted.chunk_id == original.chunk_id
        assert persisted.body == original.body

    async def test_reapproval_is_rejected_without_renewing_review_dates(self) -> None:
        prepared = await self._ingest()
        await self._make_approvable(prepared.version_id)
        await self._approve(prepared.version_id)
        approved = await KnowledgeVersion.get(version_id=prepared.version_id)
        original_verified_at = approved.verified_at
        original_review_due_at = approved.review_due_at
        later = datetime.now(UTC) + timedelta(days=100)

        with pytest.raises(ValueError, match="KNOWLEDGE_VERSION_ALREADY_REVIEWED"):
            await KnowledgeApprovalService().approve(
                prepared.version_id,
                approved_by="different-reviewer",
                verified_at=later,
                review_due_at=later + timedelta(days=365),
            )

        persisted = await KnowledgeVersion.get(version_id=prepared.version_id)
        assert persisted.verified_at == original_verified_at
        assert persisted.review_due_at == original_review_due_at
        assert persisted.approved_by == "medical-reviewer"

    async def test_manifest_style_reingestion_cannot_touch_approved_version(self) -> None:
        request = _request(
            KnowledgeSourceKind.STRUCTURED_API,
            b'{"guidance":"reviewed source"}',
            "application/json",
        )
        prepared = await self._ingest(request)
        await self._make_approvable(prepared.version_id)
        await self._approve(prepared.version_id)

        with pytest.raises(ValueError, match="APPROVED_VERSION_IMMUTABLE"):
            await self._ingest(request)

    async def test_new_approval_deprecates_previous_current_version(self) -> None:
        first_request = _request(
            KnowledgeSourceKind.STRUCTURED_API,
            b'{"guidance":"first reviewed version"}',
            "application/json",
        )
        first = await self._ingest(first_request)
        await self._make_approvable(first.version_id)
        await self._approve(first.version_id)

        second = await self._ingest(
            replace(
                first_request,
                version_label="2026-10",
                payload=b'{"guidance":"second reviewed version"}',
            )
        )
        await self._make_approvable(second.version_id)
        await self._approve(second.version_id, reviewer="next-medical-reviewer")

        previous = await KnowledgeVersion.get(version_id=first.version_id)
        current = await KnowledgeVersion.get(version_id=second.version_id)
        assert previous.approval_status is ApprovalStatus.DEPRECATED
        assert previous.is_current is False
        assert previous.current_approved_key is None
        assert current.approval_status is ApprovalStatus.APPROVED
        assert current.is_current is True
        assert current.current_approved_key == str(current.document_id)

    async def test_extractor_change_requires_new_version_label(self) -> None:
        request = _request(
            KnowledgeSourceKind.STRUCTURED_API,
            b'{"guidance":"stable source bytes"}',
            "application/json",
        )
        prepared = await self._ingest(request)
        await KnowledgeVersion.filter(version_id=prepared.version_id).update(extractor_version="older-extractor")

        with pytest.raises(ValueError, match="VERSION_EXTRACTOR_MISMATCH"):
            await self._ingest(request)
