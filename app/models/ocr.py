from datetime import UTC, datetime
from enum import StrEnum

from tortoise import fields, models
from tortoise.fields import OnDelete


class OcrJobStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OcrDocumentType(StrEnum):
    EMR = "EMR"
    PRESCRIPTION = "PRESCRIPTION"
    LAB_RESULT = "LAB_RESULT"


class OcrJob(models.Model):
    """A clinic-scoped OCR execution for one visit."""

    ocr_job_id = fields.CharField(max_length=64, primary_key=True)
    hospital_id = fields.BigIntField()
    visit = fields.ForeignKeyField(
        "models.Visit",
        related_name="ocr_jobs",
        on_delete=OnDelete.RESTRICT,
        source_field="visit_id",
    )
    status = fields.CharEnumField(enum_type=OcrJobStatus, default=OcrJobStatus.PROCESSING)
    progress = fields.SmallIntField(default=0)
    requested_by = fields.BigIntField()
    started_at = fields.DatetimeField(auto_now_add=True)
    completed_at = fields.DatetimeField(null=True)
    failure_code = fields.CharField(max_length=64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_job"
        indexes = (
            ("hospital_id", "status", "created_at"),
            ("visit", "created_at"),
        )


class OcrResult(models.Model):
    """Versioned OCR output and its review/confirmation audit metadata."""

    ocr_result_id = fields.BigIntField(primary_key=True)
    job = fields.OneToOneField(
        "models.OcrJob",
        related_name="result",
        on_delete=OnDelete.CASCADE,
        source_field="ocr_job_id",
    )
    model_name = fields.CharField(max_length=100)
    model_version = fields.CharField(max_length=50, null=True)
    version = fields.IntField(default=1)
    modified_by = fields.BigIntField(null=True)
    modified_at = fields.DatetimeField(null=True)
    confirmed_by = fields.BigIntField(null=True)
    confirmed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_result"


class OcrJobDocument(models.Model):
    """An uploaded document queued in one OCR execution."""

    ocr_job_document_id = fields.BigIntField(primary_key=True)
    job = fields.ForeignKeyField(
        "models.OcrJob",
        related_name="source_documents",
        on_delete=OnDelete.CASCADE,
        source_field="ocr_job_id",
    )
    document_id = fields.BigIntField()
    document_type = fields.CharEnumField(enum_type=OcrDocumentType)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_job_document"
        unique_together = (("job", "document_id"),)
        indexes = (("document_id",),)


class OcrDocumentText(models.Model):
    """Temporary OCR text; it must be purged with the approved source document."""

    ocr_document_text_id = fields.BigIntField(primary_key=True)
    result = fields.ForeignKeyField(
        "models.OcrResult",
        related_name="documents",
        on_delete=OnDelete.CASCADE,
        source_field="ocr_result_id",
    )
    document_id = fields.BigIntField()
    document_type = fields.CharEnumField(enum_type=OcrDocumentType)
    raw_text = fields.TextField(null=True)
    raw_text_purged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_document_text"
        unique_together = (("result", "document_id"),)

    def purge_raw_text(self, *, purged_at: datetime | None = None) -> None:
        self.raw_text = None
        self.raw_text_purged_at = purged_at or datetime.now(UTC)


class OcrField(models.Model):
    """A structured value with OCR, correction, and confirmation provenance."""

    ocr_field_id = fields.BigIntField(primary_key=True)
    result = fields.ForeignKeyField(
        "models.OcrResult",
        related_name="fields",
        on_delete=OnDelete.CASCADE,
        source_field="ocr_result_id",
    )
    document_text = fields.ForeignKeyField(
        "models.OcrDocumentText",
        related_name="fields",
        on_delete=OnDelete.SET_NULL,
        source_field="ocr_document_text_id",
        null=True,
    )
    field_type = fields.CharField(max_length=64)
    extracted_value = fields.TextField(null=True)
    corrected_value = fields.TextField(null=True)
    confidence = fields.DecimalField(max_digits=5, decimal_places=4, null=True)
    version = fields.IntField(default=1)
    is_confirmed = fields.BooleanField(default=False)
    modified_by = fields.BigIntField(null=True)
    modified_at = fields.DatetimeField(null=True)
    confirmed_by = fields.BigIntField(null=True)
    confirmed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_field"
        indexes = (("result", "field_type"),)

    @property
    def value(self) -> str | None:
        return self.corrected_value if self.corrected_value is not None else self.extracted_value


class OcrFieldCandidate(models.Model):
    """A ranked alternative retained when one field has multiple readings."""

    ocr_field_candidate_id = fields.BigIntField(primary_key=True)
    field = fields.ForeignKeyField(
        "models.OcrField",
        related_name="candidates",
        on_delete=OnDelete.CASCADE,
        source_field="ocr_field_id",
    )
    candidate_value = fields.TextField()
    confidence = fields.DecimalField(max_digits=5, decimal_places=4, null=True)
    rank = fields.SmallIntField()
    source_date = fields.DateField(null=True)
    is_selected = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_field_candidate"
        unique_together = (("field", "rank"),)
