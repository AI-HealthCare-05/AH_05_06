from datetime import datetime
from enum import StrEnum

from tortoise import fields, models
from tortoise.fields import OnDelete
from tortoise.timezone import now
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.visits import Visit


def confidence_validators() -> list[MinValueValidator | MaxValueValidator]:
    return [MinValueValidator(0), MaxValueValidator(1)]


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
    visit: fields.ForeignKeyRelation[Visit] = fields.ForeignKeyField(
        "models.Visit",
        related_name="ocr_jobs",
        on_delete=OnDelete.RESTRICT,
        source_field="visit_id",
    )
    status = fields.CharEnumField(enum_type=OcrJobStatus, default=OcrJobStatus.PROCESSING)
    progress = fields.SmallIntField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    requested_by = fields.BigIntField()
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    failure_code = fields.CharField(max_length=64, null=True)
    excluded_from_guide = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    source_documents: fields.ReverseRelation["OcrJobDocument"]

    class Meta:
        table = "ocr_job"
        indexes = (
            ("hospital_id", "status", "created_at"),
            ("visit", "created_at"),
        )


class OcrResult(models.Model):
    """Versioned OCR output and its review/confirmation audit metadata."""

    ocr_result_id = fields.BigIntField(primary_key=True)
    ocr_job_id: str
    ocr_job: fields.OneToOneRelation[OcrJob] = fields.OneToOneField(
        "models.OcrJob",
        related_name="result",
        on_delete=OnDelete.CASCADE,
    )
    model_name = fields.CharField(max_length=100)
    model_version = fields.CharField(max_length=50, null=True)
    version = fields.IntField(default=1, validators=[MinValueValidator(1)])
    modified_by = fields.BigIntField(null=True)
    modified_at = fields.DatetimeField(null=True)
    confirmed_by = fields.BigIntField(null=True)
    confirmed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    # 역참조 어노테이션은 클래스 마지막에 둔다 — 위에 두면 이후의 `fields.XField(...)`가
    # 이 어노테이션의 `fields` 속성으로 가려져 mypy가 tortoise fields 모듈을 못 찾는다.
    documents: fields.ReverseRelation["OcrDocumentText"]
    fields: fields.ReverseRelation["OcrField"]

    class Meta:
        table = "ocr_result"


class OcrJobDocument(models.Model):
    """An uploaded document queued in one OCR execution."""

    ocr_job_document_id = fields.BigIntField(primary_key=True)
    ocr_job: fields.ForeignKeyRelation[OcrJob] = fields.ForeignKeyField(
        "models.OcrJob",
        related_name="source_documents",
        on_delete=OnDelete.CASCADE,
    )
    document_id = fields.BigIntField()
    document_type = fields.CharEnumField(enum_type=OcrDocumentType)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_job_document"
        unique_together = (("ocr_job", "document_id"),)
        indexes = (("document_id",),)


class OcrDocumentText(models.Model):
    """Temporary OCR text; it must be purged with the approved source document."""

    ocr_document_text_id = fields.BigIntField(primary_key=True)
    ocr_result: fields.ForeignKeyRelation[OcrResult] = fields.ForeignKeyField(
        "models.OcrResult",
        related_name="documents",
        on_delete=OnDelete.CASCADE,
    )
    document_id = fields.BigIntField()
    document_type = fields.CharEnumField(enum_type=OcrDocumentType)
    raw_text: str | None = fields.TextField(null=True)
    raw_text_purged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_document_text"
        unique_together = (("ocr_result", "document_id"),)

    def purge_raw_text(self, *, purged_at: datetime | None = None) -> None:
        self.raw_text = None
        self.raw_text_purged_at = purged_at or now()


class OcrField(models.Model):
    """A structured value with OCR, correction, and confirmation provenance."""

    ocr_field_id = fields.BigIntField(primary_key=True)
    ocr_result: fields.ForeignKeyRelation[OcrResult] = fields.ForeignKeyField(
        "models.OcrResult",
        related_name="fields",
        on_delete=OnDelete.CASCADE,
    )
    document_text_id: int | None
    document_text: fields.ForeignKeyNullableRelation[OcrDocumentText] = fields.ForeignKeyField(
        "models.OcrDocumentText",
        related_name="fields",
        on_delete=OnDelete.SET_NULL,
        source_field="ocr_document_text_id",
        null=True,
    )
    field_type = fields.CharField(max_length=64)
    unit = fields.CharField(max_length=32, null=True)
    extracted_value = fields.TextField(null=True)
    corrected_value: str | None = fields.TextField(null=True)
    source_line = fields.IntField(null=True)
    is_pending_report = fields.BooleanField(default=False)
    confidence = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=confidence_validators(),
    )
    version = fields.IntField(default=1, validators=[MinValueValidator(1)])
    is_confirmed = fields.BooleanField(default=False)
    modified_by = fields.BigIntField(null=True)
    modified_at = fields.DatetimeField(null=True)
    # **비울 수 있다고 적어 둔다.** 칼럼은 처음부터 nullable 인데 형만 안 적혀
    # 있어서, 값이 바뀔 때 확정 도장을 떼는 자리(`_drop_confirmation`)가 mypy 에
    # 걸렸다. 뗄 수 있다는 것이 이 두 칸의 성질이다 (KEY-273).
    confirmed_by: int | None = fields.BigIntField(null=True)  # type: ignore[assignment]
    confirmed_at: datetime | None = fields.DatetimeField(null=True)  # type: ignore[assignment]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_field"
        unique_together = (("ocr_result", "field_type"),)

    @property
    def value(self) -> str | None:
        return self.corrected_value if self.corrected_value is not None else self.extracted_value

    # 역참조 어노테이션은 클래스 마지막에 둔다 — 위에 두면 이후의 `fields.XField(...)`가
    # 이 어노테이션의 `fields` 속성으로 가려져 mypy가 tortoise fields 모듈을 못 찾는다.
    candidates: fields.ReverseRelation["OcrFieldCandidate"]


class OcrFieldCandidate(models.Model):
    """A ranked alternative retained when one field has multiple readings."""

    ocr_field_candidate_id = fields.BigIntField(primary_key=True)
    ocr_field: fields.ForeignKeyRelation[OcrField] = fields.ForeignKeyField(
        "models.OcrField",
        related_name="candidates",
        on_delete=OnDelete.CASCADE,
    )
    document_text_id: int | None
    document_text: fields.ForeignKeyNullableRelation[OcrDocumentText] = fields.ForeignKeyField(
        "models.OcrDocumentText",
        related_name="candidate_fields",
        on_delete=OnDelete.SET_NULL,
        source_field="ocr_document_text_id",
        null=True,
    )
    candidate_value = fields.TextField()
    confidence = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=confidence_validators(),
    )
    rank = fields.SmallIntField(validators=[MinValueValidator(1)])
    source_date = fields.DateField(null=True)
    source_line = fields.IntField(null=True)
    is_selected = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_field_candidate"
        unique_together = (("ocr_field", "rank"),)
