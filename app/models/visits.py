from enum import StrEnum

from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.patients import Patient


class VisitStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class Visit(models.Model):
    """One clinic-scoped encounter belonging to exactly one patient."""

    visit_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    patient: fields.ForeignKeyRelation[Patient] = fields.ForeignKeyField(
        "models.Patient",
        related_name="visits",
        on_delete=OnDelete.RESTRICT,
        source_field="patient_id",
    )
    doctor_id = fields.BigIntField(null=True)
    department = fields.CharField(max_length=100, null=True)
    visited_at = fields.DatetimeField()
    visit_summary = fields.TextField(null=True)
    doctor_note = fields.TextField(null=True)
    status = fields.CharEnumField(enum_type=VisitStatus, default=VisitStatus.COMPLETED)
    planned_stop = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "visit"
        indexes = (
            ("hospital_id", "visited_at"),
            ("patient", "visited_at"),
        )
