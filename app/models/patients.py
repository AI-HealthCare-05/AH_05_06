from enum import StrEnum

from tortoise import fields, models


class PatientGender(StrEnum):
    FEMALE = "FEMALE"
    MALE = "MALE"


class Patient(models.Model):
    """A clinic-scoped patient identity shared by all visits."""

    patient_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    hospital_patient_no = fields.CharField(max_length=50)
    name = fields.CharField(max_length=50)
    birth_date = fields.DateField()
    gender = fields.CharEnumField(enum_type=PatientGender)
    phone = fields.CharField(max_length=20)
    sms_consent = fields.BooleanField(default=False)
    sms_consented_at = fields.DatetimeField(null=True)
    sms_opted_out_at = fields.DatetimeField(null=True)
    sms_consent_updated_by = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "patient"
        unique_together = (("hospital_id", "hospital_patient_no"),)
        indexes = (
            ("hospital_id", "name", "birth_date"),
            ("hospital_id", "phone"),
        )
