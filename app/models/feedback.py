"""Patient feedback records for KEY-239.

The model deliberately stores only the guide and hospital scope needed by the
admin workflow. Patient link tokens, OTP values, patient session values, and
chatbot message text do not belong in this table.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from tortoise import fields, models
from tortoise.fields import OnDelete

if TYPE_CHECKING:
    from app.models.visits import GuideDocument, PatientUsageEvent


class PatientFeedbackTarget(StrEnum):
    CHATBOT_RESPONSE = "CHATBOT_RESPONSE"
    GUIDE_SECTION = "GUIDE_SECTION"


class PatientFeedbackCategory(StrEnum):
    HELPFUL = "HELPFUL"
    UNHELPFUL = "UNHELPFUL"
    WRONG = "WRONG"
    HARD_TO_UNDERSTAND = "HARD_TO_UNDERSTAND"
    UNSAFE = "UNSAFE"
    OTHER = "OTHER"


class PatientFeedbackSourceScreen(StrEnum):
    P6 = "P6"
    P9 = "P9"


class PatientFeedback(models.Model):
    """One idempotent rating or error report submitted by a patient."""

    patient_feedback_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    guide_document: fields.ForeignKeyRelation[GuideDocument] = fields.ForeignKeyField(
        "models.GuideDocument",
        related_name="patient_feedback",
        on_delete=OnDelete.CASCADE,
        source_field="guide_document_id",
    )
    guide_document_id: int
    usage_event: fields.ForeignKeyNullableRelation[PatientUsageEvent] = fields.ForeignKeyField(
        "models.PatientUsageEvent",
        related_name="patient_feedback",
        on_delete=OnDelete.SET_NULL,
        source_field="patient_usage_event_id",
        null=True,
    )
    usage_event_id: int | None

    target = fields.CharEnumField(enum_type=PatientFeedbackTarget)
    source_screen = fields.CharEnumField(enum_type=PatientFeedbackSourceScreen)
    section_key = fields.CharField(max_length=50, null=True)
    content_key = fields.CharField(max_length=100, null=True)
    detected_tab = fields.CharField(max_length=100, null=True)
    category = fields.CharEnumField(enum_type=PatientFeedbackCategory)
    details = fields.TextField(null=True)

    # A client-generated UUID is hashed before persistence. Reusing the same
    # submission ID after a network retry returns the original row.
    idempotency_digest = fields.CharField(max_length=64)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "patient_feedback"
        unique_together = (("guide_document", "idempotency_digest"),)
        indexes = (
            ("hospital_id", "created_at"),
            ("hospital_id", "target", "category"),
        )
