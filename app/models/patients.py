from datetime import datetime
from enum import StrEnum

from tortoise import fields, models


class PatientGender(StrEnum):
    FEMALE = "FEMALE"
    MALE = "MALE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class Patient(models.Model):
    """A clinic-scoped patient identity shared by all visits."""

    patient_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    hospital_patient_no = fields.CharField(max_length=50)
    name = fields.CharField(max_length=50)
    birth_date = fields.DateField()
    gender = fields.CharEnumField(enum_type=PatientGender, default=PatientGender.UNKNOWN)
    phone = fields.CharField(max_length=20)
    sms_consent = fields.BooleanField(default=False)
    sms_consented_at: datetime | None = fields.DatetimeField(null=True)
    sms_opted_out_at: datetime | None = fields.DatetimeField(null=True)
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


class PatientNumberCorrection(models.Model):
    """환자번호를 누가·왜 고쳤는지. **한 번 쓰면 고치지 않는다.**

    환자번호 정정은 의무기록 정정이다. 계약 §6 이 `correction_reason` 을
    `hospital_patient_no` 와 **짝으로 강제**하는 이유가 여기 있다 — 사유 없이는
    정정 자체를 받지 않는다. 그런데 그 사유가 어디에도 저장되지 않고 있었다
    (`#39` 리뷰 · KEY-121). 직원은 사유를 적었고 `200` 을 받았으니 기록된 줄 안다.

    무엇을 남기는가 — 「나중에 이 정정을 되짚을 수 있는가」로 골랐다.

        before · after   무엇이 무엇으로 바뀌었나
        reason           왜 (직원이 적은 문장 그대로)
        corrected_by     누가
        hospital · patient  어느 의원의 누구
        created_at       언제

    `Patient` 를 참조하는 FK 를 쓰지 않고 `patient_id` 를 값으로 들고 있다.
    환자가 지워져도 **정정 이력은 남아야 하기 때문**이다 — 감사 기록이 대상의
    생존에 매달리면 지우는 것으로 이력을 없앨 수 있다. `hospital_id` 도 같은
    이유로 사본을 든다. 「그때 어느 의원이었나」는 지금 값이 아니라 그때 값이다.

    **왜 전용 표인가** — 범용 `event_log` 를 여기서 만들면 아직 정해지지 않은
    설계를 앞지른다(KEY-136 이 그 결정을 다룬다). 이 저장소는 이미 안내문에
    `GuideEvent` 라는 도메인 전용 이벤트 표를 두는 쪽을 골랐고, 여기도 같은
    모양이다. 칸이 타입을 갖게 되어 JSON 안을 뒤지지 않아도 된다.
    """

    correction_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    patient_id = fields.BigIntField()
    #: 바뀌기 **전** 번호. `patient.hospital_patient_no` 와 길이를 맞춘다.
    before_no = fields.CharField(max_length=50)
    after_no = fields.CharField(max_length=50)
    #: 직원이 적은 문장. `PatientUpdateRequest.correction_reason` 과 같은 상한이다.
    reason = fields.CharField(max_length=500)
    corrected_by = fields.BigIntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "patient_number_correction"
        # 한 환자의 정정 이력을 시간순으로 읽는 것이 유일한 조회 모양이다.
        # `hospital_id` 를 앞에 두어 다른 의원 것을 스캔하지 않는다.
        indexes = (("hospital_id", "patient_id", "created_at"),)
