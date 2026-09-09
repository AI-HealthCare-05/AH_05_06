"""승인 의료지식 원문·버전·청크 저장 모델 — KEY-276.

환자 문서 OCR(`MedicalDocument`)와 별개다. 이 표에는 환자 정보가 아니라
검증된 공공/기관 의료지식만 들어간다. 원문은 DB가 아닌 private object storage에
두고, DB에는 추적 가능한 메타데이터와 검색용 청크만 저장한다.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.catalog import ApprovalStatus, SourceGrade


class KnowledgeSourceKind(StrEnum):
    TEXT_PDF = "text_pdf"
    SCANNED_DOCUMENT = "scanned_document"
    STRUCTURED_API = "structured_api"


class KnowledgeIngestionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    RETRYABLE_FAILURE = "retryable_failure"
    FAILED = "failed"


class KnowledgeDocument(models.Model):
    """출처 하나의 고정 식별자. 내용 변경은 `KnowledgeVersion`으로 남긴다."""

    document_id = fields.UUIDField(primary_key=True)
    # 공통 지식은 NULL, 병원별 검수 자료는 해당 hospital_id를 가진다.
    hospital_id: int | None = fields.BigIntField(null=True)  # type: ignore[assignment]
    source_key = fields.CharField(max_length=64, unique=True)
    title = fields.CharField(max_length=300)
    source_org = fields.CharField(max_length=200)
    source_url: str | None = fields.CharField(max_length=1000, null=True)  # type: ignore[assignment]
    source_kind = fields.CharEnumField(enum_type=KnowledgeSourceKind)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    versions: fields.ReverseRelation["KnowledgeVersion"]

    class Meta:
        table = "knowledge_document"
        indexes = (("hospital_id", "source_kind"),)


class KnowledgeVersion(models.Model):
    """검증·승인의 단위인 지식 문서 버전.

    MySQL 8에는 조건부 유니크 인덱스가 없으므로 현재 승인 버전에만
    `current_approved_key=document_id`를 채운다. nullable unique 컬럼은 NULL을
    여러 개 허용하므로 문서당 현재 승인 버전이 둘이 되는 경합을 DB가 막는다.
    """

    version_id = fields.UUIDField(primary_key=True)
    document: fields.ForeignKeyRelation[KnowledgeDocument] = fields.ForeignKeyField(
        "models.KnowledgeDocument",
        related_name="versions",
        on_delete=OnDelete.RESTRICT,
        source_field="document_id",
    )
    document_id: UUID
    version_label = fields.CharField(max_length=100)
    source_sha256 = fields.CharField(max_length=64)
    source_object_key = fields.CharField(max_length=1000)
    source_mime_type = fields.CharField(max_length=100)
    license_basis: str | None = fields.CharField(max_length=500, null=True)  # type: ignore[assignment]
    license_verified = fields.BooleanField(default=False)
    source_grade = fields.CharEnumField(enum_type=SourceGrade, default=SourceGrade.C)
    verified_at: datetime | None = fields.DatetimeField(null=True)
    review_due_at: datetime | None = fields.DatetimeField(null=True)
    approval_status = fields.CharEnumField(enum_type=ApprovalStatus, default=ApprovalStatus.DRAFT)
    is_current = fields.BooleanField(default=False)
    current_approved_key: str | None = fields.CharField(max_length=36, null=True, unique=True)  # type: ignore[assignment]
    approved_by: str | None = fields.CharField(max_length=100, null=True)  # type: ignore[assignment]
    approved_at: datetime | None = fields.DatetimeField(null=True)
    extractor_version = fields.CharField(max_length=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    chunks: fields.ReverseRelation["KnowledgeChunkRecord"]
    attempts: fields.ReverseRelation["KnowledgeIngestionAttempt"]

    class Meta:
        table = "knowledge_version"
        unique_together = (("document", "version_label"),)
        indexes = (("approval_status", "is_current", "review_due_at"), ("source_sha256",))


class KnowledgeChunkRecord(models.Model):
    """검색에 쓰는 정규화 텍스트와 로컬 임베딩."""

    chunk_id = fields.UUIDField(primary_key=True)
    version: fields.ForeignKeyRelation[KnowledgeVersion] = fields.ForeignKeyField(
        "models.KnowledgeVersion",
        related_name="chunks",
        on_delete=OnDelete.CASCADE,
        source_field="version_id",
    )
    version_id: UUID
    section_key = fields.CharField(max_length=100)
    position = fields.IntField()
    body = fields.TextField()
    body_sha256 = fields.CharField(max_length=64)
    claim_key: str | None = fields.CharField(max_length=200, null=True)  # type: ignore[assignment]
    claim_value: str | None = fields.CharField(max_length=500, null=True)  # type: ignore[assignment]
    embedding: fields.Field[list[float]] = fields.JSONField()
    embedding_model = fields.CharField(max_length=300)
    embedding_revision = fields.CharField(max_length=100)
    embedding_dimension = fields.IntField()
    page_number: int | None = fields.IntField(null=True)  # type: ignore[assignment]
    bounding_boxes: fields.Field[list[dict[str, float]] | None] = fields.JSONField(null=True)
    ocr_confidence: float | None = fields.FloatField(null=True)  # type: ignore[assignment]
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "knowledge_chunk"
        unique_together = (("version", "position"),)
        indexes = (("version", "section_key"), ("body_sha256",))


class KnowledgeIngestionAttempt(models.Model):
    """원문을 남기지 않는 적재 실행·재시도 상태."""

    attempt_id = fields.UUIDField(primary_key=True)
    version: fields.ForeignKeyRelation[KnowledgeVersion] = fields.ForeignKeyField(
        "models.KnowledgeVersion",
        related_name="attempts",
        on_delete=OnDelete.CASCADE,
        source_field="version_id",
    )
    version_id: UUID
    status = fields.CharEnumField(enum_type=KnowledgeIngestionStatus, default=KnowledgeIngestionStatus.PENDING)
    attempt_count = fields.IntField(default=0)
    error_code: str | None = fields.CharField(max_length=100, null=True)  # type: ignore[assignment]
    retryable = fields.BooleanField(default=False)
    next_retry_at: datetime | None = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "knowledge_ingestion_attempt"
        indexes = (("status", "next_retry_at"),)
