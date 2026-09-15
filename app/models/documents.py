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
    #: 원본 삭제 완료 시각 — KEY-349. 첫 문자 발송 직전에 채운다.
    #:
    #: `file_path`는 지우지 않는다 — 기존 404 FILE_PURGED 응답(판독 화면
    #: 미리보기)과 감사 추적이 그 값에 기대고 있다. 실제 파일은
    #: `app/core/storage.py`의 delete()로 지운다. 이 칸은 "지웠다"는
    #: 사실만 남긴다 — 지운 시각이 곧 그 증거다.
    source_deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medical_document"
        indexes = (("hospital_id", "visit"),)
