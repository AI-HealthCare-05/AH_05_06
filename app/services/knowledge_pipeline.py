"""승인 의료지식 적재·승인 파이프라인 — KEY-276.

생성 기능과 연결하지 않는다. 원문은 private object storage에 먼저 보관하고,
추출·로컬 임베딩이 성공한 버전만 승인 후보가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

from tortoise.timezone import now as db_now
from tortoise.transactions import in_transaction

from app.models.catalog import ApprovalStatus, SourceGrade
from app.models.knowledge import (
    KnowledgeChunkRecord,
    KnowledgeDocument,
    KnowledgeIngestionAttempt,
    KnowledgeIngestionStatus,
    KnowledgeSourceKind,
    KnowledgeVersion,
)
from app.services.knowledge_extraction import (
    EXTRACTOR_VERSION,
    ExtractedChunk,
    OcrExtractor,
    extract_scanned_document,
    extract_structured_api_snapshot,
    extract_text_pdf,
)
from app.services.knowledge_search import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from app.services.knowledge_storage import PrivateObjectStore


class EmbeddingProvider(Protocol):
    model: str
    revision: str
    dimension: int

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class LocalSentenceTransformerEmbeddingProvider:
    """KEY-82에서 고정한 로컬 모델·revision만 허용하는 임베딩 공급자."""

    model = EMBEDDING_MODEL
    revision = EMBEDDING_MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    def __init__(self) -> None:
        self._encoder: Any | None = None

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        import asyncio

        def _encode() -> tuple[tuple[float, ...], ...]:
            if self._encoder is None:
                try:
                    from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
                except ImportError as exc:
                    raise RuntimeError("LOCAL_EMBEDDING_NOT_INSTALLED") from exc
                self._encoder = SentenceTransformer(self.model, revision=self.revision)
            vectors = self._encoder.encode(list(texts), normalize_embeddings=True)
            result = tuple(tuple(float(value) for value in vector) for vector in vectors)
            if any(len(vector) != self.dimension for vector in result):
                raise RuntimeError("EMBEDDING_DIMENSION_MISMATCH")
            return result

        return await asyncio.to_thread(_encode)


@dataclass(frozen=True)
class KnowledgeIngestionRequest:
    title: str
    source_org: str
    source_url: str
    version_label: str
    source_kind: KnowledgeSourceKind
    payload: bytes
    mime_type: str
    hospital_id: int | None = None
    license_basis: str | None = None


@dataclass(frozen=True)
class PreparedVersion:
    document_id: str
    version_id: str
    attempt_id: str
    source_object_key: str


class KnowledgeRepository(Protocol):
    async def prepare(
        self,
        request: KnowledgeIngestionRequest,
        *,
        source_key: str,
        source_sha256: str,
        object_key: str,
    ) -> PreparedVersion: ...

    async def store_chunks(
        self,
        prepared: PreparedVersion,
        chunks: tuple[ExtractedChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
        provider: EmbeddingProvider,
    ) -> None: ...

    async def mark_attempt(
        self,
        attempt_id: str,
        status: KnowledgeIngestionStatus,
        *,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> None: ...


def stable_source_key(request: KnowledgeIngestionRequest) -> str:
    scope = str(request.hospital_id) if request.hospital_id is not None else "common"
    identity = "\n".join((scope, request.source_org.strip(), request.source_url.strip(), request.title.strip()))
    return sha256(identity.encode("utf-8")).hexdigest()


def private_source_object_key(request: KnowledgeIngestionRequest, source_key: str, digest: str) -> str:
    scope = str(request.hospital_id) if request.hospital_id is not None else "common"
    safe_version = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in request.version_label)[:100]
    return f"knowledge/{scope}/{source_key}/{safe_version}/{digest}.source"


def _safe_error_code(exc: Exception) -> str:
    message = str(exc)
    if message and len(message) <= 100 and message.replace("_", "").isalnum():
        return message.upper()
    return exc.__class__.__name__.upper()[:100]


def _is_retryable_ingestion_error(exc: Exception) -> bool:
    """입력·계약 위반은 재시도하지 않고, 외부/인프라 실패만 재시도한다."""

    return not isinstance(exc, ValueError)


class KnowledgeIngestionService:
    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        object_store: PrivateObjectStore,
        embedding_provider: EmbeddingProvider,
        ocr_extractor: OcrExtractor | None = None,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._embedding_provider = embedding_provider
        self._ocr_extractor = ocr_extractor

    async def ingest(self, request: KnowledgeIngestionRequest) -> PreparedVersion:
        if not request.payload:
            raise ValueError("SOURCE_EMPTY")
        if not request.source_org.strip() or not request.source_url.strip():
            raise ValueError("SOURCE_IDENTITY_INCOMPLETE")

        digest = sha256(request.payload).hexdigest()
        source_key = stable_source_key(request)
        object_key = private_source_object_key(request, source_key, digest)
        prepared = await self._repository.prepare(
            request,
            source_key=source_key,
            source_sha256=digest,
            object_key=object_key,
        )
        await self._repository.mark_attempt(prepared.attempt_id, KnowledgeIngestionStatus.PROCESSING)
        try:
            await self._object_store.put(object_key, request.payload, request.mime_type)
            stored_payload = await self._object_store.get(object_key)
            chunks = await self._extract(request, stored_payload)
            vectors = await self._embedding_provider.embed(tuple(chunk.body for chunk in chunks))
            if len(chunks) != len(vectors):
                raise RuntimeError("EMBEDDING_COUNT_MISMATCH")
            await self._repository.store_chunks(prepared, chunks, vectors, self._embedding_provider)
        except Exception as exc:
            retryable = _is_retryable_ingestion_error(exc)
            await self._repository.mark_attempt(
                prepared.attempt_id,
                (
                    KnowledgeIngestionStatus.RETRYABLE_FAILURE
                    if retryable
                    else KnowledgeIngestionStatus.FAILED
                ),
                error_code=_safe_error_code(exc),
                retryable=retryable,
            )
            raise
        await self._repository.mark_attempt(prepared.attempt_id, KnowledgeIngestionStatus.READY)
        return prepared

    async def _extract(
        self,
        request: KnowledgeIngestionRequest,
        payload: bytes,
    ) -> tuple[ExtractedChunk, ...]:
        if request.source_kind is KnowledgeSourceKind.TEXT_PDF:
            return extract_text_pdf(payload)
        if request.source_kind is KnowledgeSourceKind.STRUCTURED_API:
            return extract_structured_api_snapshot(payload)
        if self._ocr_extractor is None:
            raise RuntimeError("OCR_EXTRACTOR_NOT_CONFIGURED")
        return await extract_scanned_document(payload, request.mime_type, self._ocr_extractor)


class TortoiseKnowledgeRepository:
    """버전/청크 멱등성과 실패 상태를 한 DB에 저장한다."""

    async def prepare(
        self,
        request: KnowledgeIngestionRequest,
        *,
        source_key: str,
        source_sha256: str,
        object_key: str,
    ) -> PreparedVersion:
        async with in_transaction() as connection:
            document, _ = await KnowledgeDocument.get_or_create(
                source_key=source_key,
                defaults={
                    "hospital_id": request.hospital_id,
                    "title": request.title.strip(),
                    "source_org": request.source_org.strip(),
                    "source_url": request.source_url.strip(),
                    "source_kind": request.source_kind,
                },
                using_db=connection,
            )
            version, created = await KnowledgeVersion.get_or_create(
                document=document,
                version_label=request.version_label,
                defaults={
                    "source_sha256": source_sha256,
                    "source_object_key": object_key,
                    "source_mime_type": request.mime_type,
                    "license_basis": request.license_basis,
                    "extractor_version": EXTRACTOR_VERSION,
                },
                using_db=connection,
            )
            if not created and version.source_sha256 != source_sha256:
                raise ValueError("VERSION_CONTENT_MISMATCH")
            if not created and version.extractor_version != EXTRACTOR_VERSION:
                raise ValueError("VERSION_EXTRACTOR_MISMATCH")
            attempt = await KnowledgeIngestionAttempt.create(version=version, using_db=connection)
        return PreparedVersion(
            document_id=str(document.document_id),
            version_id=str(version.version_id),
            attempt_id=str(attempt.attempt_id),
            source_object_key=object_key,
        )

    async def store_chunks(
        self,
        prepared: PreparedVersion,
        chunks: tuple[ExtractedChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
        provider: EmbeddingProvider,
    ) -> None:
        if any(len(vector) != provider.dimension for vector in vectors):
            raise ValueError("EMBEDDING_DIMENSION_MISMATCH")
        hashes = [sha256(chunk.body.encode("utf-8")).hexdigest() for chunk in chunks]
        async with in_transaction() as connection:
            version = (
                await KnowledgeVersion.filter(version_id=prepared.version_id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if version is None:
                raise ValueError("KNOWLEDGE_VERSION_NOT_FOUND")
            existing = (
                await KnowledgeChunkRecord.filter(version_id=prepared.version_id)
                .using_db(connection)
                .order_by("position")
            )
            if version.approval_status is not ApprovalStatus.DRAFT or version.approved_at is not None:
                raise ValueError("APPROVED_VERSION_IMMUTABLE")
            if len(existing) == len(chunks) and all(
                row.position == chunk.position
                and row.body_sha256 == digest
                and row.embedding_model == provider.model
                and row.embedding_revision == provider.revision
                for row, chunk, digest in zip(existing, chunks, hashes, strict=True)
            ):
                return
            await KnowledgeChunkRecord.filter(version_id=prepared.version_id).using_db(connection).delete()
            await KnowledgeChunkRecord.bulk_create(
                [
                    KnowledgeChunkRecord(
                        version_id=prepared.version_id,
                        section_key=chunk.section_key,
                        position=chunk.position,
                        body=chunk.body,
                        body_sha256=digest,
                        embedding=list(vector),
                        embedding_model=provider.model,
                        embedding_revision=provider.revision,
                        embedding_dimension=provider.dimension,
                        page_number=chunk.page_number,
                        bounding_boxes=list(chunk.bounding_boxes) or None,
                        ocr_confidence=chunk.ocr_confidence,
                    )
                    for chunk, vector, digest in zip(chunks, vectors, hashes, strict=True)
                ],
                using_db=connection,
            )

    async def mark_attempt(
        self,
        attempt_id: str,
        status: KnowledgeIngestionStatus,
        *,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        values: dict[str, object] = {
            "status": status,
            "error_code": error_code,
            "retryable": retryable,
        }
        if status is KnowledgeIngestionStatus.PROCESSING:
            attempt = await KnowledgeIngestionAttempt.get(attempt_id=attempt_id)
            values["attempt_count"] = attempt.attempt_count + 1
        if retryable:
            values["next_retry_at"] = db_now() + timedelta(minutes=5)
        await KnowledgeIngestionAttempt.filter(attempt_id=attempt_id).update(**values)


class KnowledgeApprovalService:
    """검증 완료 버전을 현재 승인본으로 원자적으로 교체한다."""

    async def approve(
        self,
        version_id: str,
        *,
        approved_by: str,
        verified_at: datetime,
        review_due_at: datetime | None,
    ) -> None:
        now = db_now()
        if review_due_at is not None and review_due_at <= now:
            raise ValueError("REVIEW_ALREADY_EXPIRED")
        async with in_transaction() as connection:
            version = (
                await KnowledgeVersion.filter(version_id=version_id).using_db(connection).select_for_update().first()
            )
            if version is None:
                raise ValueError("KNOWLEDGE_VERSION_NOT_FOUND")
            if version.approval_status is not ApprovalStatus.DRAFT or version.approved_at is not None:
                raise ValueError("KNOWLEDGE_VERSION_ALREADY_REVIEWED")
            document = await KnowledgeDocument.filter(document_id=version.document_id).using_db(connection).get()
            if version.source_grade is not SourceGrade.A:
                raise ValueError("SOURCE_GRADE_NOT_APPROVABLE")
            if not version.license_verified or not document.source_url or not document.source_org:
                raise ValueError("SOURCE_VERIFICATION_INCOMPLETE")
            if not await KnowledgeChunkRecord.filter(version_id=version_id).using_db(connection).exists():
                raise ValueError("KNOWLEDGE_CHUNKS_NOT_READY")
            if (
                not await KnowledgeIngestionAttempt.filter(
                    version_id=version_id,
                    status=KnowledgeIngestionStatus.READY,
                )
                .using_db(connection)
                .exists()
            ):
                raise ValueError("KNOWLEDGE_INGESTION_NOT_READY")

            await (
                KnowledgeVersion.filter(
                    document_id=version.document_id,
                    approval_status=ApprovalStatus.APPROVED,
                    is_current=True,
                )
                .using_db(connection)
                .update(
                    approval_status=ApprovalStatus.DEPRECATED,
                    is_current=False,
                    current_approved_key=None,
                )
            )
            version.approval_status = ApprovalStatus.APPROVED
            version.is_current = True
            version.current_approved_key = str(version.document_id)
            version.approved_by = approved_by
            version.approved_at = now
            version.verified_at = verified_at
            version.review_due_at = review_due_at
            await version.save(using_db=connection)
