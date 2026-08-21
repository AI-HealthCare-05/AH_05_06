from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.ocr import OcrDocumentType
from app.models.visits import Visit


class MedicalDocument(models.Model):
    """An uploaded medical document stored temporarily before OCR and source deletion."""

    document_id = fields.BigIntField(primary_key=True, generated=True)
    hospital_id = fields.BigIntField()
    visit: fields.ForeignKeyRelation[Visit] = fields.ForeignKeyField(
        "models.Visit",
        related_name="documents",
        on_delete=OnDelete.RESTRICT,
        source_field="visit_id",
    )
    document_type = fields.CharEnumField(enum_type=OcrDocumentType, null=True)
    file_path = fields.CharField(max_length=500)
    file_size = fields.BigIntField()
    mime_type = fields.CharField(max_length=100)
    uploaded_by = fields.BigIntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medical_document"
        indexes = (("hospital_id", "visit"),)
